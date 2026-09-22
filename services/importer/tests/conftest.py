from __future__ import annotations

from collections.abc import Iterator
from os import environ
from pathlib import Path
import uuid

import psycopg
import pytest

from importer.config import StorageSettings, database_url_from_environment, storage_from_environment


REPOSITORY_MIGRATIONS = Path(environ.get("DB_DIR", "/db")) / "migrations"


def _with_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


@pytest.fixture
def database_url() -> Iterator[str]:
    admin_url = database_url_from_environment()
    name = f"vinolog_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as connection:
            connection.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL is not available: {error}")
    try:
        yield _with_database(admin_url, name)
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def migrations_dir() -> Path:
    if not REPOSITORY_MIGRATIONS.is_dir():
        pytest.skip(f"Migrations directory is not mounted: {REPOSITORY_MIGRATIONS}")
    return REPOSITORY_MIGRATIONS


@pytest.fixture
def storage_settings() -> StorageSettings:
    return storage_from_environment()
