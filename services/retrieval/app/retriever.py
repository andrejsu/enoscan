"""Wine label visual retriever — a standalone service, not a layer inside the
existing OCR-driven scanner (see app/service.py, app/main.py, which this
module never imports and never affects).

Self-contained: label normalization -> DINOv2 embedding -> ANN candidate
shortlist -> SIFT + RANSAC geometric verification -> one combined visual
confidence score. Runs behind its own process (app/retriever_main.py), its
own index file/format (retriever_index.py, build_retriever_index.py), and
its own compose service — see compose.yaml's retriever/retriever-index
services. The only sanctioned touchpoint with the existing app is temporary:
apps/web's scanner can be pointed at this service's port for visual testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import time

import numpy as np

from .embedding import Dinov2Encoder
from .embedding_store import EmbeddingStore
from .retriever_index import Candidate, IndexedReference, RetrieverIndex
from .label_normalize import Config as LabelConfig, Segmenter, prepare_query


SIFT_WEIGHT = 0.45
EMBEDDING_WEIGHT = 0.55
EMBEDDING_SHORTLIST_LIMIT = 20
DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class RetrievalResult:
    candidates: list[Candidate]
    ocr_image: np.ndarray
    used_sam: bool
    warnings: list[str]
    timing: dict[str, int] = field(default_factory=dict)


class VisualRetriever:
    def __init__(self, index: RetrieverIndex, *, encoder: Dinov2Encoder | None = None,
                 embedding_store: EmbeddingStore | None = None, build_id: int | None = None,
                 segmenter: Segmenter | None = None, label_config: LabelConfig | None = None,
                 use_sam: bool = False, visual_limit: int = 24,
                 embedding_limit: int = EMBEDDING_SHORTLIST_LIMIT) -> None:
        if not 1 <= visual_limit <= 200:
            raise ValueError("visual_limit must be between 1 and 200")
        if not 1 <= embedding_limit <= 200:
            raise ValueError("embedding_limit must be between 1 and 200")
        self.index = index
        self.encoder = encoder
        self.embedding_store = embedding_store
        self.build_id = build_id
        self.segmenter = segmenter
        self.label_config = label_config or LabelConfig()
        self.use_sam = use_sam
        self.visual_limit = visual_limit
        self.embedding_limit = embedding_limit
        self._reference_by_slug: dict[str, IndexedReference] = {r.wine.slug: r for r in index.references}

    def search(self, image: np.ndarray, *, limit: int = DEFAULT_LIMIT) -> RetrievalResult:
        started = time.perf_counter()
        prepared = prepare_query(image, segmenter=self.segmenter, config=self.label_config,
                                 fast=not self.use_sam)
        normalize_ms = round((time.perf_counter() - started) * 1000)

        embed_started = time.perf_counter()
        embedding_scores: dict[str, float] = {}
        embedding_slugs: list[str] = []
        query_vector: np.ndarray | None = None
        uses_embeddings = self.encoder is not None and self.embedding_store is not None and self.build_id is not None
        if uses_embeddings:
            query_vector = self.encoder.encode_one(prepared.visual)
            nearest = self.embedding_store.nearest(self.build_id, query_vector, self.embedding_limit)
            embedding_scores = dict(nearest)
            embedding_slugs = [slug for slug, _ in nearest]
        embedding_ms = round((time.perf_counter() - embed_started) * 1000)

        result = self.index.search(prepared.visual, limit=max(limit, self.embedding_limit),
                                   visual_limit=self.visual_limit, extra_slugs=tuple(embedding_slugs))
        by_slug = {c.wine.slug: c for c in result.candidates}
        for slug in embedding_slugs:
            reference = self._reference_by_slug.get(slug)
            if reference is not None:
                by_slug.setdefault(slug, Candidate(reference.wine, reference.image_sha256, 0.0, 0, 0))

        if uses_embeddings and query_vector is not None:
            scores_started = time.perf_counter()
            unscored = [slug for slug in by_slug if slug not in embedding_scores]
            embedding_scores.update(self.embedding_store.scores(self.build_id, query_vector, unscored))
            embedding_ms += round((time.perf_counter() - scores_started) * 1000)

        candidates = [
            replace(candidate, score=round(min(1.0,
                SIFT_WEIGHT * candidate.score
                + EMBEDDING_WEIGHT * max(0.0, embedding_scores.get(candidate.wine.slug, 0.0))
            ), 4))
            for candidate in by_slug.values()
        ]
        candidates.sort(key=lambda item: (item.score, item.inliers, item.good_matches), reverse=True)

        return RetrievalResult(
            candidates=candidates[:limit],
            ocr_image=prepared.ocr,
            used_sam=prepared.used_sam,
            warnings=prepared.warnings,
            timing={
                "normalizeMs": normalize_ms,
                "embeddingMs": embedding_ms,
                "featuresMs": result.feature_ms,
                "searchMs": result.search_ms,
            },
        )
