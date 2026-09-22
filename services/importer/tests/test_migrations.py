from pathlib import Path

import psycopg
import pytest

from importer.migrations import apply_migrations


def test_applies_files_in_name_order_once(database_url: str, tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("INSERT INTO steps VALUES ('second');", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("CREATE TABLE steps (name text); INSERT INTO steps VALUES ('first');",
                                            encoding="utf-8")

    assert apply_migrations(database_url, tmp_path) == ["001_first.sql", "002_second.sql"]
    assert apply_migrations(database_url, tmp_path) == []

    with psycopg.connect(database_url) as connection:
        steps = [row[0] for row in connection.execute("SELECT name FROM steps").fetchall()]
        recorded = connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    assert steps == ["first", "second"]
    assert recorded == 2


def test_refuses_changed_migration(database_url: str, tmp_path: Path) -> None:
    migration = tmp_path / "001_first.sql"
    migration.write_text("CREATE TABLE steps (name text);", encoding="utf-8")
    apply_migrations(database_url, tmp_path)

    migration.write_text("CREATE TABLE steps (name text, extra text);", encoding="utf-8")
    with pytest.raises(SystemExit, match="changed"):
        apply_migrations(database_url, tmp_path)


def test_failed_migration_is_not_recorded(database_url: str, tmp_path: Path) -> None:
    (tmp_path / "001_broken.sql").write_text("CREATE TABLE ok (id int); SELECT missing_function();",
                                             encoding="utf-8")
    with pytest.raises(psycopg.Error):
        apply_migrations(database_url, tmp_path)

    with psycopg.connect(database_url) as connection:
        recorded = connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        table = connection.execute("SELECT to_regclass('public.ok')").fetchone()[0]
    assert recorded == 0
    assert table is None


def test_repository_schema_applies(database_url: str, migrations_dir: Path) -> None:
    apply_migrations(database_url, migrations_dir)
    with psycopg.connect(database_url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        extension = connection.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert {
        "import_runs", "catalog_rows_raw", "wines", "images", "image_sources", "wine_images",
        "image_overrides", "import_issues", "index_builds", "index_references", "image_embeddings",
    } <= tables
    assert extension == ("vector",)
