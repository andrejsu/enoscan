"""SIFT + DINOv2 index for the standalone wine-label retriever.

Deliberately a separate class from index.py's SiftIndex, which belongs to
the existing OCR-driven service (app/service.py, app/main.py). That service
must not be affected by anything tuned here — this index carries its own
FLANN parameters and per-query feature budget, chosen for the retriever's own
~3s / low-memory targets, on its own .npz file (see build_retriever_index.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time

import cv2
import numpy as np

from .catalog import Wine
from .image_features import ImageFeatures, extract_features


# Hard ceiling on how many candidates get a full SIFT+RANSAC rerank per
# search, independent of visual_limit and however large the embedding
# extra_slugs union is. Reranking is the single biggest non-SAM latency cost.
RERANK_CAP = 40


@dataclass(frozen=True)
class IndexedReference:
    wine: Wine
    relative_path: str
    mapping_kind: str
    mapping_score: float


@dataclass(frozen=True)
class Candidate:
    wine: Wine
    relative_path: str
    score: float
    good_matches: int
    inliers: int


@dataclass(frozen=True)
class SearchResult:
    candidates: list[Candidate]
    feature_ms: int
    search_ms: int
    visual_slugs: list[str] = field(default_factory=list)


class RetrieverIndex:
    def __init__(
        self,
        references: list[IndexedReference],
        keypoints: np.ndarray,
        descriptors: np.ndarray,
        owners: np.ndarray,
        offsets: np.ndarray,
        embeddings: np.ndarray | None = None,
    ) -> None:
        self.references = references
        self.keypoints = keypoints
        self.descriptors = descriptors
        self.owners = owners
        self.offsets = offsets
        # trees=2/checks=32 (vs. a more typical trees=4/checks=64): a full
        # 2098-reference index at trees=4 measured ~2.65GB resident and,
        # combined with SAM, got OOM-killed under real load. This index is
        # its own file/process, so the trade only affects the retriever.
        self.matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 2}, {"checks": 32})
        self.matcher.add([self.descriptors])
        self.matcher.train()
        self.embeddings: np.ndarray | None = None
        if embeddings is not None and len(embeddings):
            if len(embeddings) != len(references):
                raise ValueError("embeddings must have one row per reference")
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            self.embeddings = (embeddings / np.maximum(norms, 1e-8)).astype(np.float32)

    @classmethod
    def load(cls, path: str) -> "RetrieverIndex":
        with np.load(path, allow_pickle=False) as data:
            raw_references = json.loads(str(data["references_json"].item()))
            references = [
                IndexedReference(
                    wine=Wine(**item["wine"]),
                    relative_path=item["relative_path"],
                    mapping_kind=item["mapping_kind"],
                    mapping_score=item["mapping_score"],
                )
                for item in raw_references
            ]
            return cls(
                references=references,
                keypoints=data["keypoints"].astype(np.float32),
                descriptors=data["descriptors"].astype(np.float32),
                owners=data["owners"].astype(np.int32),
                offsets=data["offsets"].astype(np.int64),
                embeddings=data["embeddings"].astype(np.float32) if "embeddings" in data else None,
            )

    def embedding_scores(self, query: np.ndarray) -> dict[str, float]:
        """Cosine similarity of a normalized DINOv2 query vector to every
        reference, keyed by slug. Empty if this index has no embeddings."""
        if self.embeddings is None:
            return {}
        similarities = self.embeddings @ query
        return {self.references[i].wine.slug: float(similarities[i]) for i in range(len(self.references))}

    def search(self, image: np.ndarray, *, limit: int = 5, extra_slugs: tuple[str, ...] = (),
               visual_limit: int = 24) -> SearchResult:
        if not 1 <= visual_limit <= 200:
            raise ValueError("visual_limit must be between 1 and 200")
        started = time.perf_counter()
        query = extract_features(image, max_side=1600, feature_count=800)
        feature_ms = round((time.perf_counter() - started) * 1000)
        if len(query.descriptors) < 2:
            return SearchResult(candidates=[], feature_ms=feature_ms, search_ms=0)

        search_started = time.perf_counter()
        neighbors = self.matcher.knnMatch(query.descriptors, k=8)
        votes: dict[int, float] = {}
        for matches in neighbors:
            seen: set[int] = set()
            for match in matches:
                owner = int(self.owners[match.trainIdx])
                if owner in seen:
                    continue
                seen.add(owner)
                votes[owner] = votes.get(owner, 0.0) + max(0.0, 1.25 - match.distance)

        shortlist = sorted(votes, key=votes.get, reverse=True)[:visual_limit]
        visual_slugs = list(dict.fromkeys(self.references[i].wine.slug for i in shortlist))
        extra = set(extra_slugs)
        shortlist = list(dict.fromkeys(shortlist + [i for i, ref in enumerate(self.references) if ref.wine.slug in extra]))
        shortlist = shortlist[:max(visual_limit, RERANK_CAP)]
        candidates = [self._rerank(owner, query) for owner in shortlist]
        candidates.sort(key=lambda item: (item.score, item.inliers, item.good_matches), reverse=True)
        search_ms = round((time.perf_counter() - search_started) * 1000)
        unique = {}
        for candidate in candidates:
            unique.setdefault(candidate.wine.slug, candidate)
        return SearchResult(candidates=list(unique.values())[:limit], feature_ms=feature_ms, search_ms=search_ms,
                            visual_slugs=visual_slugs)

    def _rerank(self, owner: int, query: ImageFeatures) -> Candidate:
        start, end = int(self.offsets[owner]), int(self.offsets[owner + 1])
        reference_descriptors = self.descriptors[start:end]
        reference_points = self.keypoints[start:end]
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        pairs = matcher.knnMatch(query.descriptors, reference_descriptors, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.78 * pair[1].distance]

        inliers = 0
        if len(good) >= 4:
            query_points = np.float32([query.keypoints[match.queryIdx] for match in good]).reshape(-1, 1, 2)
            matched_reference_points = np.float32([reference_points[match.trainIdx] for match in good]).reshape(-1, 1, 2)
            _, mask = cv2.findHomography(matched_reference_points, query_points, cv2.RANSAC, 5.0)
            if mask is not None:
                inliers = int(mask.sum())

        evidence = (inliers * 2.0) + min(len(good), 40)
        score = evidence / (evidence + 60.0)
        return Candidate(
            wine=self.references[owner].wine,
            relative_path=self.references[owner].relative_path,
            score=round(score, 4),
            good_matches=len(good),
            inliers=inliers,
        )


def save_index(
    path: str,
    references: list[IndexedReference],
    features: list[ImageFeatures],
    embeddings: np.ndarray | None = None,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    offsets = [0]
    descriptor_parts: list[np.ndarray] = []
    keypoint_parts: list[np.ndarray] = []
    owner_parts: list[np.ndarray] = []

    for owner, item in enumerate(features):
        descriptor_parts.append(item.descriptors)
        keypoint_parts.append(item.keypoints)
        owner_parts.append(np.full(len(item.descriptors), owner, dtype=np.int32))
        offsets.append(offsets[-1] + len(item.descriptors))

    references_json = json.dumps([
        {
            "wine": reference.wine.__dict__,
            "relative_path": reference.relative_path,
            "mapping_kind": reference.mapping_kind,
            "mapping_score": reference.mapping_score,
        }
        for reference in references
    ], ensure_ascii=False)
    if embeddings is not None and len(embeddings) != len(references):
        raise ValueError("embeddings must have one row per reference")
    temporary_path = output.with_suffix(f"{output.suffix}.tmp.npz")
    extra = {"embeddings": embeddings.astype(np.float32)} if embeddings is not None else {}
    np.savez_compressed(
        temporary_path,
        references_json=np.array(references_json),
        descriptors=np.concatenate(descriptor_parts),
        keypoints=np.concatenate(keypoint_parts),
        owners=np.concatenate(owner_parts),
        offsets=np.array(offsets, dtype=np.int64),
        **extra,
    )
    temporary_path.replace(output)
