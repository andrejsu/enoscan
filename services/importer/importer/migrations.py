from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg


LOCK_KEY = "vinolog-migrations"


def migration_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.sql") if path.is_file())


def apply_migrations(database_url: str, directory: Path) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(hashtext(%s))", (LOCK_KEY,))
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  filename text PRIMARY KEY,
                  sha256 text NOT NULL,
                  applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            applied = dict(connection.execute("SELECT filename, sha256 FROM schema_migrations").fetchall())
            for path in migration_files(directory):
                content = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                known = applied.get(path.name)
                if known is not None:
                    if known != digest:
                        raise SystemExit(f"Migration {path.name} changed after it was applied.")
                    continue
                with connection.transaction():
                    connection.execute(content)
                    connection.execute(
                        "INSERT INTO schema_migrations (filename, sha256) VALUES (%s, %s)",
                        (path.name, digest),
                    )
                applied_now.append(path.name)
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
    return applied_now
