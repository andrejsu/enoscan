"""SIFT + RANSAC reference index, shared by the visual retriever (app/visual)
and the legacy SIFT baseline (app/baseline). One algorithm; each owner keeps
its own tuning (SiftSearchConfig) and its own .npz object (index kind), so
tuning one never moves the other."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time

import cv2
import numpy as np

from .catalog.models import Wine
from .image_features import ImageFeatures, extract_features


@dataclass(frozen=True)
class SiftSearchConfig:
    """FLANN effort, the query's feature budget and how many shortlisted
    references at most get the RANSAC rerank (None: every one)."""
    trees: int
    checks: int
    feature_count: int
    rerank_cap: int | None = None


@dataclass(frozen=True)
class IndexedReference:
    wine: Wine
    image_sha256: str


@dataclass(frozen=True)
class Candidate:
    wine: Wine
    score: float
    good_matches: int
    inliers: int


@dataclass(frozen=True)
class SearchResult:
    candidates: list[Candidate]
    feature_ms: int
    search_ms: int
    visual_slugs: list[str] = field(default_factory=list)


class SiftIndex:
    def __init__(
        self,
        references: list[IndexedReference],
        keypoints: np.ndarray,
        descriptors: np.ndarray,
        owners: np.ndarray,
        offsets: np.ndarray,
        config: SiftSearchConfig,
    ) -> None:
        self.references = references
        self.keypoints = keypoints
        self.descriptors = descriptors
        self.owners = owners
        self.offsets = offsets
        self.config = config
        self.matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": config.trees}, {"checks": config.checks})
        self.matcher.add([self.descriptors])
        self.matcher.train()

    @classmethod
    def load(cls, path: str, config: SiftSearchConfig) -> "SiftIndex":
        with np.load(path, allow_pickle=False) as data:
            references = [
                IndexedReference(wine=Wine.from_json(item["wine"]), image_sha256=item["image_sha256"])
                for item in json.loads(str(data["references_json"].item()))
            ]
            return cls(
                references=references,
                keypoints=data["keypoints"].astype(np.float32),
                descriptors=data["descriptors"].astype(np.float32),
                owners=data["owners"].astype(np.int32),
                offsets=data["offsets"].astype(np.int64),
                config=config,
            )

    def search(self, image: np.ndarray, *, limit: int = 5, extra_slugs: tuple[str, ...] = (),
               visual_limit: int = 24) -> SearchResult:
        if not 1 <= visual_limit <= 200:
            raise ValueError("visual_limit must be between 1 and 200")
        started = time.perf_counter()
        query = extract_features(image, max_side=1600, feature_count=self.config.feature_count)
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
        if self.config.rerank_cap is not None:
            shortlist = shortlist[:max(visual_limit, self.config.rerank_cap)]
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
            score=round(score, 4),
            good_matches=len(good),
            inliers=inliers,
        )


def save_index(
    path: str,
    references: list[IndexedReference],
    features: list[ImageFeatures],
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
        {"wine": reference.wine.to_json(), "image_sha256": reference.image_sha256}
        for reference in references
    ], ensure_ascii=False)
    temporary_path = output.with_suffix(f"{output.suffix}.tmp.npz")
    np.savez_compressed(
        temporary_path,
        references_json=np.array(references_json),
        descriptors=np.concatenate(descriptor_parts),
        keypoints=np.concatenate(keypoint_parts),
        owners=np.concatenate(owner_parts),
        offsets=np.array(offsets, dtype=np.int64),
    )
    temporary_path.replace(output)
