from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
import time

import psycopg
from psycopg.types.json import Jsonb

from .archive import ArchiveMember, ArchiveStats, iter_originals
from .catalog_csv import CatalogParseResult, Issue, read_catalog
from .config import ARCHIVE_FILENAMES, BUCKETS, CATALOG_FILENAME, Settings
from .eval_sets import upload_eval_sets
from .images import ImageDecodeError, ingest_image
from .mapping import SourceImage, mark_suspicious, resolve_mappings, shared_images
from .migrations import apply_migrations
from .overrides import Override, apply_overrides, read_overrides
from .storage import ObjectStore
from .versioning import DatasetFingerprint, archive_sha256, file_sha256, optional_file_sha256


IMPORT_LOCK_KEY = "vinolog-import"
PROGRESS_EVERY = 200

ArchiveReader = Callable[[Path, ArchiveStats], Iterator[ArchiveMember]]


def prepare_storage(settings: Settings, store: ObjectStore | None = None) -> ObjectStore:
    applied = apply_migrations(settings.database_url, settings.migrations_dir)
    for name in applied:
        print(f"Applied migration {name}.")
    store = store or ObjectStore(settings.storage)
    for bucket in BUCKETS:
        store.ensure_bucket(bucket)
    return store


def required_inputs(input_dir: Path) -> tuple[Path, list[Path]]:
    catalog = input_dir / CATALOG_FILENAME
    archives = [input_dir / name for name in ARCHIVE_FILENAMES]
    missing = [path.name for path in [catalog, *archives] if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing dataset files in data/dataset/: {', '.join(missing)}")
    return catalog, archives


def fingerprint_inputs(settings: Settings, catalog: Path, archives: list[Path]) -> DatasetFingerprint:
    return DatasetFingerprint(
        catalog_sha256=file_sha256(catalog),
        archive_sha256=archive_sha256(archives),
        overrides_sha256=optional_file_sha256(settings.overrides_path),
    )


def run_import(
    settings: Settings,
    archive_reader: ArchiveReader = iter_originals,
    store: ObjectStore | None = None,
) -> str:
    store = prepare_storage(settings, store)
    catalog_path, archives = required_inputs(settings.input_dir)
    started = time.perf_counter()
    fingerprint = fingerprint_inputs(settings, catalog_path, archives)
    version = fingerprint.dataset_version
    print(f"Dataset version {version} (hashed in {time.perf_counter() - started:.1f}s).")

    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(hashtext(%s))", (IMPORT_LOCK_KEY,))
        if latest_succeeded_version(connection) == version:
            print(f"Dataset {version} already imported.")
            return version

        overrides = read_overrides(settings.overrides_path)
        catalog = read_catalog(catalog_path)
        run_id = connection.execute(
            """
            INSERT INTO import_runs (dataset_version, catalog_sha256, archive_sha256, overrides_sha256,
                                     mapping_algo_version, preview_version, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'running')
            RETURNING id
            """,
            (version, fingerprint.catalog_sha256, fingerprint.archive_sha256, fingerprint.overrides_sha256,
             fingerprint.mapping_algo_version, fingerprint.preview_version),
        ).fetchone()[0]

        try:
            stats: dict[str, object] = {}
            issues: list[Issue] = list(catalog.issues)
            timings: dict[str, float] = {}

            stage = time.perf_counter()
            if archive_already_ingested(connection, fingerprint):
                print("Archive unchanged since the last import; skipping image extraction.")
                stats["images_ingested"] = False
            else:
                archive_stats, image_issues = ingest_archive(
                    connection, store, archives[0], fingerprint.archive_sha256, archive_reader,
                )
                issues.extend(image_issues)
                stats["images_ingested"] = True
                stats["archive_originals"] = archive_stats.originals
                stats["archive_skipped"] = dict(archive_stats.skipped)
            timings["images"] = time.perf_counter() - stage

            stage = time.perf_counter()
            eval_counts, eval_issues = upload_eval_sets(settings.input_dir, store)
            issues.extend(eval_issues)
            stats["eval_objects"] = eval_counts
            timings["eval"] = time.perf_counter() - stage

            stage = time.perf_counter()
            with connection.transaction():
                stats.update(write_catalog_state(
                    connection, run_id, fingerprint.archive_sha256, catalog, overrides, issues,
                ))
                timings["catalog"] = time.perf_counter() - stage
                stats["timings_seconds"] = {key: round(value, 1) for key, value in timings.items()}
                connection.execute(
                    """
                    UPDATE import_runs
                    SET status = 'succeeded', stats = %s, finished_at = now()
                    WHERE id = %s
                    """,
                    (Jsonb(stats), run_id),
                )
        except BaseException as error:
            connection.execute(
                "UPDATE import_runs SET status = 'failed', error = %s, finished_at = now() WHERE id = %s",
                (f"{type(error).__name__}: {error}", run_id),
            )
            raise

    print(f"Imported dataset {version}: {summarize(stats)}")
    return version


def latest_succeeded_version(connection: psycopg.Connection) -> str | None:
    row = connection.execute(
        "SELECT dataset_version FROM import_runs WHERE status = 'succeeded' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def archive_already_ingested(connection: psycopg.Connection, fingerprint: DatasetFingerprint) -> bool:
    row = connection.execute(
        """
        SELECT archive_sha256, preview_version
        FROM import_runs
        WHERE status = 'succeeded'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return row == (fingerprint.archive_sha256, fingerprint.preview_version)


def ingest_archive(
    connection: psycopg.Connection,
    store: ObjectStore,
    first_volume: Path,
    archive_sha: str,
    archive_reader: ArchiveReader,
) -> tuple[ArchiveStats, list[Issue]]:
    stats = ArchiveStats()
    issues: list[Issue] = []
    started = time.perf_counter()
    for position, member in enumerate(archive_reader(first_volume, stats), start=1):
        try:
            ingest_image(member, store, connection, archive_sha)
        except ImageDecodeError as error:
            issues.append(Issue("image_decode_failed", None, {"strapi_path": member.strapi_path, "error": str(error)}))
        if position % PROGRESS_EVERY == 0:
            print(f"Ingested {position} images in {time.perf_counter() - started:.0f}s.", flush=True)
    print(f"Ingested {stats.originals} images in {time.perf_counter() - started:.0f}s; "
          f"skipped {dict(stats.skipped)}.", flush=True)
    return stats, issues


def load_sources(connection: psycopg.Connection, archive_sha: str) -> list[SourceImage]:
    rows = connection.execute(
        """
        SELECT s.strapi_path, s.filename, s.image_sha256, i.size_bytes
        FROM image_sources s
        JOIN images i ON i.sha256 = s.image_sha256
        WHERE s.archive_sha256 = %s
        ORDER BY s.strapi_path
        """,
        (archive_sha,),
    ).fetchall()
    return [SourceImage(*row) for row in rows]


def write_catalog_state(
    connection: psycopg.Connection,
    run_id: int,
    archive_sha: str,
    catalog: CatalogParseResult,
    overrides: list[Override],
    issues: list[Issue],
) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO catalog_rows_raw (run_id, row_no, payload) VALUES (%s, %s, %s)",
            [(run_id, row_no, Jsonb(payload)) for row_no, payload in catalog.raw_rows],
        )
        cursor.executemany(
            """
            INSERT INTO wines (slug, name, category, color, region, grape_varieties, description, winery,
                               source_image_filename, source_row_no, raw_record_count, is_active,
                               first_seen_run_id, updated_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET
              name = EXCLUDED.name,
              category = EXCLUDED.category,
              color = EXCLUDED.color,
              region = EXCLUDED.region,
              grape_varieties = EXCLUDED.grape_varieties,
              description = EXCLUDED.description,
              winery = EXCLUDED.winery,
              source_image_filename = EXCLUDED.source_image_filename,
              source_row_no = EXCLUDED.source_row_no,
              raw_record_count = EXCLUDED.raw_record_count,
              is_active = true,
              updated_run_id = EXCLUDED.updated_run_id
            """,
            [
                (wine.slug, wine.name, wine.category, wine.color, wine.region, list(wine.grape_varieties),
                 wine.description, wine.winery, wine.source_image_filename, wine.source_row_no,
                 wine.raw_record_count, run_id, run_id)
                for wine in catalog.wines
            ],
        )
    active_slugs = [wine.slug for wine in catalog.wines]
    deactivated = connection.execute(
        """
        UPDATE wines SET is_active = false, updated_run_id = %s
        WHERE is_active AND NOT (slug = ANY(%s))
        RETURNING slug
        """,
        (run_id, active_slugs),
    ).fetchall()
    for (slug,) in deactivated:
        issues.append(Issue("wine_deactivated", slug, {}))

    sources = load_sources(connection, archive_sha)
    resolved = resolve_mappings(catalog.wines, sources)
    mappings, override_issues = apply_overrides(resolved, overrides, set(active_slugs), sources)
    issues.extend(override_issues)
    mappings = mark_suspicious(mappings)
    for sha, slugs in shared_images(mappings).items():
        issues.append(Issue("shared_image", None, {"image_sha256": sha, "slugs": slugs}))

    connection.execute("DELETE FROM wine_images")
    connection.execute("DELETE FROM image_sources WHERE archive_sha256 <> %s", (archive_sha,))
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO wine_images (slug, image_sha256, strapi_path, is_primary, mapping_kind, mapping_score,
                                     review_status, run_id)
            VALUES (%s, %s, %s, true, %s, %s, %s, %s)
            """,
            [
                (m.slug, m.image_sha256, m.strapi_path, m.mapping_kind, m.mapping_score, m.review_status, run_id)
                for m in mappings
            ],
        )
        cursor.execute("DELETE FROM image_overrides")
        cursor.executemany(
            """
            INSERT INTO image_overrides (line_no, slug, action, strapi_filename, note, run_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [(o.line_no, o.slug, o.action, o.strapi_filename, o.note, run_id) for o in overrides],
        )
        cursor.executemany(
            "INSERT INTO import_issues (run_id, kind, slug, detail) VALUES (%s, %s, %s, %s)",
            [(run_id, issue.kind, issue.slug, Jsonb(issue.detail)) for issue in issues],
        )

    mapped_shas = {mapping.image_sha256 for mapping in mappings}
    distinct_images = {source.image_sha256 for source in sources}
    inactive = connection.execute("SELECT count(*) FROM wines WHERE NOT is_active").fetchone()[0]
    return {
        "catalog_rows": len(catalog.raw_rows),
        "wines": len(catalog.wines),
        "inactive_wines": inactive,
        "duplicate_slugs": sum(1 for issue in catalog.issues if issue.kind == "duplicate_slug"),
        "image_sources": len(sources),
        "images": len(distinct_images),
        "mapped": len(mappings),
        "mapping_kinds": dict(Counter(mapping.mapping_kind for mapping in mappings)),
        "suspicious": sum(1 for mapping in mappings if mapping.review_status == "suspicious"),
        "orphans": len(distinct_images - mapped_shas),
        "overrides": len(overrides),
        "issues": dict(Counter(issue.kind for issue in issues)),
    }


def summarize(stats: dict[str, object]) -> str:
    keys = ("wines", "inactive_wines", "images", "mapped", "suspicious", "orphans")
    return ", ".join(f"{key}={stats.get(key)}" for key in keys)
