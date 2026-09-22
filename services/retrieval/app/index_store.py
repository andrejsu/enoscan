from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from .storage import INDEXES_BUCKET, ObjectStore


@dataclass(frozen=True)
class IndexBuild:
    id: int
    kind: str
    dataset_version: str
    object_key: str
    reference_count: int


@dataclass(frozen=True)
class IndexedImage:
    slug: str
    image_sha256: str


def object_key_for(kind: str, version: str) -> str:
    return f"{kind}/{version}.npz"


def find_build(database_url: str, kind: str, version: str) -> IndexBuild | None:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT id, kind, dataset_version, object_key, reference_count
            FROM index_builds
            WHERE kind = %s AND dataset_version = %s
            """,
            (kind, version),
        ).fetchone()
    return IndexBuild(*row) if row else None


def register_build(database_url: str, kind: str, version: str, object_key: str,
                   references: list[IndexedImage]) -> IndexBuild:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            build_id = connection.execute(
                """
                INSERT INTO index_builds (kind, dataset_version, object_key, reference_count)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (kind, version, object_key, len(references)),
            ).fetchone()[0]
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO index_references (build_id, position, slug, image_sha256)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [(build_id, position, item.slug, item.image_sha256) for position, item in enumerate(references)],
                )
    return IndexBuild(build_id, kind, version, object_key, len(references))


def publish_index(store: ObjectStore, database_url: str, kind: str, version: str, path: Path,
                  references: list[IndexedImage]) -> IndexBuild:
    object_key = object_key_for(kind, version)
    store.put_file(INDEXES_BUCKET, object_key, path)
    return register_build(database_url, kind, version, object_key, references)


def fetch_index(store: ObjectStore, build: IndexBuild, directory: Path = Path("/tmp/vinolog-indexes")) -> Path:
    destination = directory / build.object_key
    if not destination.is_file():
        temporary = destination.with_name(f"{destination.name}.download")
        store.download_file(INDEXES_BUCKET, build.object_key, temporary)
        temporary.replace(destination)
    return destination


def require_build(database_url: str, kind: str, version: str) -> IndexBuild:
    build = find_build(database_url, kind, version)
    if build is None:
        raise RuntimeError(f"Index {kind} for dataset {version} is missing. Run the index builder first.")
    return build


def current_index_path(database_url: str, kind: str, store: ObjectStore | None = None) -> Path:
    from .catalog import current_dataset_version

    version = current_dataset_version(database_url)
    return fetch_index(store or ObjectStore(), require_build(database_url, kind, version))
