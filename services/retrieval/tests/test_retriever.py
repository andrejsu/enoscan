from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("label_prep")

from app import retriever as retriever_module
from app.catalog import Wine
from app.retriever import EMBEDDING_WEIGHT, SIFT_WEIGHT, VisualRetriever
from app.retriever_index import Candidate, IndexedReference, SearchResult


SLUGS = [f"wine-{position}" for position in range(6)]


class NumpyEmbeddingStore:
    def __init__(self, vectors: dict[str, np.ndarray]) -> None:
        self.vectors = vectors

    def nearest(self, build_id: int, query: np.ndarray, limit: int) -> list[tuple[str, float]]:
        scores = {slug: float(vector @ query) for slug, vector in self.vectors.items()}
        return [(slug, scores[slug]) for slug in sorted(scores, key=lambda s: (-scores[s], s))[:limit]]

    def scores(self, build_id: int, query: np.ndarray, slugs) -> dict[str, float]:
        return {slug: float(self.vectors[slug] @ query) for slug in slugs if slug in self.vectors}


class SiftStub:
    def __init__(self, references: list[IndexedReference], sift: dict[str, float]) -> None:
        self.references = references
        self.sift = sift

    def search(self, image, *, limit, visual_limit, extra_slugs):
        wines = {reference.wine.slug: reference.wine for reference in self.references}
        slugs = list(dict.fromkeys([*self.sift, *extra_slugs]))
        candidates = [Candidate(wines[slug], f"sha-{slug}", self.sift.get(slug, 0.0), 20, 10) for slug in slugs]
        return SearchResult(candidates=candidates, feature_ms=1, search_ms=1)


class EncoderStub:
    def __init__(self, query: np.ndarray) -> None:
        self.query = query

    def encode_one(self, image) -> np.ndarray:
        return self.query


def test_combined_scores_match_full_embedding_scan(monkeypatch) -> None:
    rng = np.random.default_rng(11)
    vectors = {slug: rng.normal(size=16) for slug in SLUGS}
    vectors = {slug: (vector / np.linalg.norm(vector)).astype(np.float32) for slug, vector in vectors.items()}
    query = vectors["wine-4"] * 0.9 + vectors["wine-1"] * 0.1
    query = (query / np.linalg.norm(query)).astype(np.float32)
    references = [IndexedReference(Wine(slug, slug, "Винодельня", has_image=True), f"sha-{slug}", "slug", 1.0)
                  for slug in SLUGS]
    sift = {"wine-0": 0.6, "wine-2": 0.3}
    monkeypatch.setattr(retriever_module, "prepare_query", lambda image, **_: SimpleNamespace(
        visual=image, ocr=image, used_sam=False, warnings=[]))

    result = VisualRetriever(
        SiftStub(references, sift), encoder=EncoderStub(query), embedding_store=NumpyEmbeddingStore(vectors),
        build_id=1, embedding_limit=2,
    ).search(np.zeros((4, 4, 3), dtype=np.uint8), limit=10)

    full_scan = {slug: float(vector @ query) for slug, vector in vectors.items()}
    expected_slugs = {"wine-0", "wine-2", *sorted(full_scan, key=full_scan.get, reverse=True)[:2]}
    expected = {
        slug: round(min(1.0, SIFT_WEIGHT * sift.get(slug, 0.0) + EMBEDDING_WEIGHT * max(0.0, full_scan[slug])), 4)
        for slug in expected_slugs
    }
    assert {candidate.wine.slug: candidate.score for candidate in result.candidates} == expected
    assert result.candidates[0].wine.slug == max(expected, key=expected.get)
