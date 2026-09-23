from __future__ import annotations

from dataclasses import dataclass, field
import time

import numpy as np

from .index import Candidate, SearchResult, SiftIndex


RESPONSE_LIMIT = 5


@dataclass(frozen=True)
class ProductResult:
    body: dict[str, object]
    diagnostics: dict[str, object] = field(default_factory=dict)


def _wine_card_with_image(candidate: Candidate) -> dict[str, object]:
    return candidate.wine.as_card()


class SearchService:
    def __init__(self, index: SiftIndex, *, visual_limit: int = 24,
                 dataset_version: str = "unversioned") -> None:
        self.index = index
        self.dataset_version = dataset_version
        if not 1 <= visual_limit <= 200:
            raise ValueError("visual_limit must be between 1 and 200")
        self.visual_limit = visual_limit

    def search(self, image: np.ndarray) -> ProductResult:
        started = time.perf_counter()
        result = self.index.search(image, limit=RESPONSE_LIMIT, visual_limit=self.visual_limit)
        total_ms = round((time.perf_counter() - started) * 1000)
        body = self._product_body(result, total_ms)
        body["version"]["configuration"] = f"sift{self.visual_limit}"
        return ProductResult(body, {"visual_slugs": result.visual_slugs})

    def _product_body(self, result: SearchResult, total_ms: int) -> dict[str, object]:
        candidates = result.candidates
        top_score = candidates[0].score if candidates else 0.0
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = max(0.0, top_score - second_score)
        top = candidates[0] if candidates else None
        wine_card = top.wine.as_card() if top else None
        alternatives = [_wine_card_with_image(item) for item in candidates[1:4]]

        if top and top.inliers >= 7 and top.good_matches >= 10 and top_score >= 0.3 and margin >= 0.04:
            status = "matched"
        elif top and top_score >= 0.12:
            status = "uncertain"
        else:
            status = "not_found"

        guidance = None
        if status == "uncertain":
            guidance = "Приблизьте этикетку, уберите блик и убедитесь, что название и год попали в кадр."
        elif status == "not_found":
            guidance = "Совпадение не подтверждено. Снимите этикетку крупнее и строго спереди."

        return {
            "status": status,
            "wine": wine_card if status == "matched" else None,
            "candidates": [{"slug": item.wine.slug, "score": item.score, "wine": _wine_card_with_image(item)} for item in candidates],
            "confidence": {
                "kind": "similarity",
                "top1Score": top_score,
                "margin": round(margin, 4),
            },
            "timing": {
                "totalMs": total_ms,
                "stages": {
                    "features": result.feature_ms,
                    "search": result.search_ms,
                },
            },
            "alternatives": alternatives,
            "version": {
                "model": "sift-ransac-v2",
                "catalog": self.dataset_version,
                "configuration": "sift-700-flann-ransac",
            },
            **({"guidance": guidance} if guidance else {}),
            "isMock": False,
        }
