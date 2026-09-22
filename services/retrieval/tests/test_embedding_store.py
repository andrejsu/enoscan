import numpy as np
import pytest

from app.embedding_store import EmbeddingStore
from app.index_store import IndexedImage, register_build

from conftest import seed_catalog


SLUGS = ["alpha", "beta", "gamma", "delta"]


def unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


@pytest.fixture
def populated(migrated_database_url: str):
    seed_catalog(migrated_database_url, SLUGS)
    rng = np.random.default_rng(7)
    vectors = {slug: unit(rng.normal(size=384)) for slug in SLUGS}
    shas = {slug: f"{position:064d}" for position, slug in enumerate(SLUGS)}
    store = EmbeddingStore(migrated_database_url, "test-model")
    store.upsert_many([(shas[slug], vectors[slug]) for slug in SLUGS[:3]])
    build = register_build(migrated_database_url, "retriever-v2", "v1", "retriever-v2/v1.npz", [
        IndexedImage(slug, shas[slug]) for slug in SLUGS
    ])
    yield store, build, vectors, shas
    store.close()


def test_missing_is_scoped_to_model(populated) -> None:
    store, _, _, shas = populated

    assert store.missing(shas.values()) == {shas["delta"]}
    other = EmbeddingStore(store.database_url, "other-model")
    assert other.missing(shas.values()) == set(shas.values())
    other.close()


def test_nearest_and_scores_match_numpy(populated) -> None:
    store, build, vectors, _ = populated
    query = unit(np.random.default_rng(3).normal(size=384))
    expected = {slug: float(vectors[slug] @ query) for slug in SLUGS[:3]}

    nearest = store.nearest(build.id, query, limit=2)
    assert [slug for slug, _ in nearest] == sorted(expected, key=expected.get, reverse=True)[:2]
    for slug, similarity in nearest:
        assert similarity == pytest.approx(expected[slug], abs=1e-5)

    scores = store.scores(build.id, query, ["gamma", "delta", "unknown"])
    assert set(scores) == {"gamma"}
    assert scores["gamma"] == pytest.approx(expected["gamma"], abs=1e-5)
