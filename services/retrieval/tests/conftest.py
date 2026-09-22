from __future__ import annotations

from collections.abc import Iterator
from os import environ
from pathlib import Path
import uuid

import psycopg
import pytest

from app.config import load_settings


MIGRATIONS = Path(environ.get("MIGRATIONS_DIR", Path(__file__).resolve().parents[3] / "db" / "migrations"))


def _with_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


@pytest.fixture
def migrated_database_url() -> Iterator[str]:
    if not MIGRATIONS.is_dir():
        pytest.skip(f"Migrations directory is not available: {MIGRATIONS}")
    admin_url = load_settings().database_url
    name = f"vinolog_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as connection:
            connection.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL is not available: {error}")
    url = _with_database(admin_url, name)
    try:
        with psycopg.connect(url, autocommit=True) as connection:
            for path in sorted(MIGRATIONS.glob("*.sql")):
                connection.execute(path.read_text(encoding="utf-8"))
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def seed_catalog(url: str, slugs: list[str]) -> None:
    with psycopg.connect(url) as connection:
        run_id = connection.execute(
            """
            INSERT INTO import_runs (dataset_version, catalog_sha256, archive_sha256, overrides_sha256,
                                     mapping_algo_version, preview_version, status)
            VALUES ('v1', 'c', 'a', 'o', 'm', 'p', 'succeeded') RETURNING id
            """
        ).fetchone()[0]
        for position, slug in enumerate(slugs):
            sha = f"{position:064d}"
            connection.execute(
                """
                INSERT INTO wines (slug, name, winery, grape_varieties, source_row_no, raw_record_count, is_active,
                                   first_seen_run_id, updated_run_id)
                VALUES (%s, %s, 'Винодельня', ARRAY['Кокур'], %s, 1, true, %s, %s)
                """,
                (slug, slug.title(), position + 1, run_id, run_id),
            )
            connection.execute(
                """
                INSERT INTO images (sha256, object_key, preview_key, mime, width, height, size_bytes, preview_version)
                VALUES (%s, %s, %s, 'image/webp', 10, 10, 10, 'p')
                """,
                (sha, f"originals/{sha}.webp", f"previews/{sha}.webp"),
            )
            connection.execute(
                "INSERT INTO image_sources (strapi_path, filename, image_sha256, archive_sha256) VALUES (%s, %s, %s, 'a')",
                (f"{slug}.webp", f"{slug}.webp", sha),
            )
            connection.execute(
                """
                INSERT INTO wine_images (slug, image_sha256, strapi_path, is_primary, mapping_kind, mapping_score,
                                         review_status, run_id)
                VALUES (%s, %s, %s, true, 'slug', 1, 'auto', %s)
                """,
                (slug, sha, f"{slug}.webp", run_id),
            )
