from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from ..sift_index import SearchResult, SiftIndex


RESPONSE_LIMIT = 5
GUIDANCE = {
    "uncertain": "Приблизьте этикетку, уберите блик и убедитесь, что название и год попали в кадр.",
    "not_found": "Совпадение не подтверждено. Снимите этикетку крупнее и строго спереди.",
}


@dataclass(frozen=True)
class ProductResult:
    body: dict[str, object]
    diagnostics: dict[str, object]


class BaselineSearch:
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
        return ProductResult(self._product_body(result, total_ms), {"visual_slugs": result.visual_slugs})

    def _product_body(self, result: SearchResult, total_ms: int) -> dict[str, object]:
        candidates = result.candidates
        top = candidates[0] if candidates else None
        top_score = top.score if top else 0.0
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = max(0.0, top_score - second_score)

        if top and top.inliers >= 7 and top.good_matches >= 10 and top_score >= 0.3 and margin >= 0.04:
            status = "matched"
        elif top and top_score >= 0.12:
            status = "uncertain"
        else:
            status = "not_found"
        guidance = GUIDANCE.get(status)

        return {
            "status": status,
            "wine": top.wine.as_card() if status == "matched" else None,
            "candidates": [{"slug": item.wine.slug, "score": item.score, "wine": item.wine.as_card()}
                           for item in candidates],
            "confidence": {"kind": "similarity", "top1Score": top_score, "margin": round(margin, 4)},
            "timing": {"totalMs": total_ms, "stages": {"features": result.feature_ms, "search": result.search_ms}},
            "alternatives": [item.wine.as_card() for item in candidates[1:4]],
            "version": {"model": "sift-ransac-v2", "catalog": self.dataset_version,
                        "configuration": f"sift{self.visual_limit}"},
            **({"guidance": guidance} if guidance else {}),
            "isMock": False,
        }
