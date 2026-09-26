"""The catalog state of one import run, written inside the run's transaction:
wines (upserted, the missing ones deactivated), image mappings with manual
overrides applied, the overrides themselves and the run's issues."""

from __future__ import annotations

from collections import Counter

import psycopg
from psycopg.types.json import Jsonb

from .catalog_csv import CatalogParseResult, Issue
from .mapping import SourceImage, mark_suspicious, resolve_mappings, shared_images
from .overrides import Override, apply_overrides


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
