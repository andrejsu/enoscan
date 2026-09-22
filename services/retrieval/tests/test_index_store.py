import psycopg

from app.catalog import current_dataset_version, load_references, load_wines
from app.index_store import IndexedImage, find_build, object_key_for, register_build

from conftest import seed_catalog


def test_object_key_is_versioned() -> None:
    assert object_key_for("sift-v3", "abc") == "sift-v3/abc.npz"


def test_register_and_find_build(migrated_database_url: str) -> None:
    seed_catalog(migrated_database_url, ["alpha", "beta"])

    assert find_build(migrated_database_url, "sift-v3", "v1") is None
    build = register_build(migrated_database_url, "sift-v3", "v1", "sift-v3/v1.npz", [
        IndexedImage("alpha", f"{0:064d}"),
        IndexedImage("beta", f"{1:064d}"),
    ])

    assert find_build(migrated_database_url, "sift-v3", "v1") == build
    with psycopg.connect(migrated_database_url) as connection:
        rows = connection.execute(
            "SELECT position, slug FROM index_references WHERE build_id = %s ORDER BY position", (build.id,)
        ).fetchall()
    assert rows == [(0, "alpha"), (1, "beta")]


def test_catalog_loaders_use_active_wines_and_primary_images(migrated_database_url: str) -> None:
    seed_catalog(migrated_database_url, ["alpha", "beta"])
    with psycopg.connect(migrated_database_url) as connection:
        connection.execute("DELETE FROM wine_images WHERE slug = 'beta'")

    assert current_dataset_version(migrated_database_url) == "v1"
    wines = {wine.slug: wine for wine in load_wines(migrated_database_url)}
    assert wines["alpha"].has_image and not wines["beta"].has_image
    assert wines["alpha"].grape_varieties == ("Кокур",)
    references = load_references(migrated_database_url)
    assert [(item.wine.slug, item.object_key) for item in references] == [
        ("alpha", f"originals/{0:064d}.webp"),
    ]
