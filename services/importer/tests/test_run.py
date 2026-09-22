from __future__ import annotations

from collections.abc import Iterator
import csv
from io import BytesIO
from pathlib import Path

from PIL import Image
import psycopg
import pytest

from importer.archive import ArchiveMember, ArchiveStats
from importer.catalog_csv import COLUMNS
from importer.config import ARCHIVE_FILENAMES, CATALOG_FILENAME, IMAGES_BUCKET, Settings, StorageSettings
from importer.run import run_import


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.buckets: set[str] = set()

    def ensure_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects

    def put_bytes(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = content

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        return [key for stored_bucket, key in self.objects if stored_bucket == bucket and key.startswith(prefix)]


class FakeArchive:
    def __init__(self, members: dict[str, bytes]) -> None:
        self.members = members
        self.reads = 0

    def __call__(self, first_volume: Path, stats: ArchiveStats) -> Iterator[ArchiveMember]:
        self.reads += 1
        for path, content in self.members.items():
            stats.originals += 1
            yield ArchiveMember(strapi_path=path, content=content)


def png(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 80), color).save(output, format="PNG")
    return output.getvalue()


def write_catalog(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def catalog_row(slug: str, photo: str, description: str = "") -> dict[str, str]:
    return {"Название вина": slug.title(), "Винодельня": "Тест", "Slug": slug, "Название фото": photo,
            "Описание": description}


@pytest.fixture
def workspace(tmp_path: Path, database_url: str, migrations_dir: Path) -> Settings:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for index, name in enumerate(ARCHIVE_FILENAMES):
        (input_dir / name).write_bytes(f"volume-{index}".encode())
    write_catalog(input_dir / CATALOG_FILENAME, [
        catalog_row("alpha", "alpha.png", "первое"),
        catalog_row("beta", "beta.png"),
        catalog_row("gamma", "gamma.png"),
    ])
    overrides = tmp_path / "image-overrides.csv"
    overrides.write_text("slug,action,strapi_filename,note\n", encoding="utf-8")
    return Settings(
        database_url=database_url,
        storage=StorageSettings("http://unused", "key", "secret", "us-east-1"),
        input_dir=input_dir,
        migrations_dir=migrations_dir,
        overrides_path=overrides,
    )


def query(settings: Settings, sql: str) -> list[tuple]:
    with psycopg.connect(settings.database_url) as connection:
        return connection.execute(sql).fetchall()


def test_full_import_then_noop(workspace: Settings) -> None:
    store = MemoryStore()
    archive = FakeArchive({
        "alpha_0123456789.png": png("red"),
        "beta_0123456789.png": png("green"),
        "copy/beta_0123456789.png": png("green"),
        "orphan_0123456789.png": png("blue"),
    })

    version = run_import(workspace, archive, store)

    assert query(workspace, "SELECT status FROM import_runs") == [("succeeded",)]
    assert query(workspace, "SELECT slug, mapping_kind FROM wine_images ORDER BY slug") == [
        ("alpha", "image_filename"), ("beta", "image_filename"),
    ]
    assert query(workspace, "SELECT count(*) FROM images") == [(3,)]
    stored = [key for bucket, key in store.objects if bucket == IMAGES_BUCKET]
    assert len([key for key in stored if key.startswith("originals/")]) == 3
    assert len([key for key in stored if key.startswith("previews/")]) == 3
    stats = query(workspace, "SELECT stats FROM import_runs")[0][0]
    assert stats["orphans"] == 1
    assert stats["issues"]["eval_set_missing"] == 2

    assert run_import(workspace, archive, store) == version
    assert archive.reads == 1
    assert query(workspace, "SELECT count(*) FROM import_runs") == [(1,)]


def test_overrides_change_skips_archive_and_catalog_change_deactivates(workspace: Settings) -> None:
    store = MemoryStore()
    archive = FakeArchive({
        "alpha_0123456789.png": png("red"),
        "beta_0123456789.png": png("green"),
        "gamma_0123456789.png": png("blue"),
    })
    run_import(workspace, archive, store)

    workspace.overrides_path.write_text(
        "slug,action,strapi_filename,note\nbeta,reject,,wrong bottle\n", encoding="utf-8",
    )
    run_import(workspace, archive, store)
    assert archive.reads == 1
    assert query(workspace, "SELECT slug FROM wine_images ORDER BY slug") == [("alpha",), ("gamma",)]

    write_catalog(workspace.input_dir / CATALOG_FILENAME, [
        catalog_row("alpha", "alpha.png", "обновлённое"),
        catalog_row("beta", "beta.png"),
    ])
    run_import(workspace, archive, store)

    assert query(workspace, "SELECT slug, is_active, description FROM wines ORDER BY slug") == [
        ("alpha", True, "обновлённое"), ("beta", True, None), ("gamma", False, None),
    ]
    assert query(workspace, "SELECT slug FROM wine_images ORDER BY slug") == [("alpha",)]
    assert query(workspace, "SELECT count(*) FROM import_runs WHERE status = 'succeeded'") == [(3,)]


def test_invalid_override_marks_run_failed(workspace: Settings) -> None:
    store = MemoryStore()
    archive = FakeArchive({"alpha_0123456789.png": png("red")})
    workspace.overrides_path.write_text(
        "slug,action,strapi_filename,note\nunknown,reject,,\n", encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="unknown or inactive slug"):
        run_import(workspace, archive, store)

    assert query(workspace, "SELECT status FROM import_runs") == [("failed",)]
    assert query(workspace, "SELECT count(*) FROM wines") == [(0,)]


def test_reverting_inputs_reimports_previous_version(workspace: Settings) -> None:
    store = MemoryStore()
    archive = FakeArchive({"alpha_0123456789.png": png("red"), "beta_0123456789.png": png("green")})
    original_overrides = workspace.overrides_path.read_text(encoding="utf-8")
    first = run_import(workspace, archive, store)

    workspace.overrides_path.write_text(original_overrides + "beta,reject,,\n", encoding="utf-8")
    run_import(workspace, archive, store)
    assert query(workspace, "SELECT slug FROM wine_images ORDER BY slug") == [("alpha",)]

    workspace.overrides_path.write_text(original_overrides, encoding="utf-8")
    assert run_import(workspace, archive, store) == first
    assert query(workspace, "SELECT slug FROM wine_images ORDER BY slug") == [("alpha",), ("beta",)]
    assert query(workspace, "SELECT count(*) FROM import_runs WHERE status = 'succeeded'") == [(3,)]
