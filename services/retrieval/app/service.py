from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import time

import numpy as np

from .index import Candidate, SearchResult, SiftIndex
from .catalog import Wine
from .ocr import extract_label, extract_year
from .text_search import TextSearch


TEXT_SHORTLIST_LIMIT = 20
RESPONSE_LIMIT = 5


@dataclass(frozen=True)
class ProductResult:
    body: dict[str, object]
    diagnostics: dict[str, object] = field(default_factory=dict)


def _wine_card_with_image(candidate: Candidate) -> dict[str, object]:
    return candidate.wine.as_card()


def year_adjustment(wine: Wine, year: int | None) -> float:
    catalog_year = extract_year(wine.name)
    if year is None or catalog_year is None:
        return 0.0
    return 0.08 if catalog_year == year else -0.08


class SearchService:
    def __init__(self, index: SiftIndex, *, catalog: list[Wine] | None = None,
                 ocr_timeout: float = 2.0, ocr_psm: int = 6,
                 ocr_preprocess: bool = True, ocr_retry: bool = False,
                 visual_limit: int = 24, dataset_version: str = "unversioned") -> None:
        self.index = index
        self.dataset_version = dataset_version
        if not 1 <= visual_limit <= 200:
            raise ValueError("visual_limit must be between 1 and 200")
        self.visual_limit = visual_limit
        if ocr_timeout <= 0 or ocr_psm not in (6, 11):
            raise ValueError("OCR timeout must be positive; OCR PSM must be 6 or 11")
        self.text_search = TextSearch(catalog if catalog is not None else [r.wine for r in index.references])
        self.ocr_options = dict(timeout=ocr_timeout, psm=ocr_psm, preprocess=ocr_preprocess, retry=ocr_retry)

    def search(self, image: np.ndarray) -> ProductResult:
        started = time.perf_counter()
        ocr_started = time.perf_counter()
        label = extract_label(image, **self.ocr_options)
        ocr_ms = round((time.perf_counter() - ocr_started) * 1000)
        text_started = time.perf_counter()
        text_scores = self.text_search.scores(label.search_text)
        text_wines = self.text_search.candidates(text_scores, limit=TEXT_SHORTLIST_LIMIT)
        text_ms = round((time.perf_counter() - text_started) * 1000)
        result = self.index.search(image, limit=self.visual_limit + TEXT_SHORTLIST_LIMIT,
                                   visual_limit=self.visual_limit, extra_slugs=tuple(w.slug for w in text_wines))
        by_slug = {c.wine.slug: c for c in result.candidates}
        for wine in text_wines:
            by_slug.setdefault(wine.slug, Candidate(wine, "", 0.0, 0, 0))
        year = int(label.year.value) if label.year else None
        candidates = [
            replace(
                candidate,
                # Reserve score headroom so saturated geometric matches can still be separated by text.
                score=round(max(0.0, min(1.0, 0.72 * candidate.score + 0.2 * text_scores.get(candidate.wine.slug, 0)
                                       + year_adjustment(candidate.wine, year))), 4),
            )
            for candidate in by_slug.values()
        ]
        candidates.sort(key=lambda item: (item.score, item.inliers, item.good_matches), reverse=True)
        result = replace(result, candidates=candidates[:RESPONSE_LIMIT])
        total_ms = round((time.perf_counter() - started) * 1000)
        body = self._product_body(result, total_ms, ocr_ms)
        if candidates and year_adjustment(candidates[0].wine, year) < 0 and body["status"] == "matched":
            body.update(status="uncertain", wine=None, guidance="Год на этикетке требует проверки. Снимите его крупнее или выберите вино из списка.")
        body["timing"]["stages"]["textSearch"] = text_ms
        body["version"]["configuration"] = f"sift{self.visual_limit}-text{TEXT_SHORTLIST_LIMIT}-tesseract-{self.ocr_options}"
        # Keep raw OCR and internal evidence out of the public response and application logs.
        return ProductResult(body, {
            "ocr": {**asdict(label), "options": self.ocr_options},
            "union_slugs": list(by_slug), "visual_slugs": result.visual_slugs,
            "text_slugs": [w.slug for w in text_wines],
            "features": [{"slug": c.wine.slug, "visual": c.score,
                          "text": text_scores.get(c.wine.slug, 0), "year": year_adjustment(c.wine, year)}
                         for c in by_slug.values()],
        })

    def _product_body(self, result: SearchResult, total_ms: int, ocr_ms: int) -> dict[str, object]:
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
                    "ocr": ocr_ms,
                },
            },
            "alternatives": alternatives,
            "version": {
                "model": "sift-ransac-text-v2",
                "catalog": self.dataset_version,
                "configuration": "sift-700-flann-ransac-tesseract",
            },
            **({"guidance": guidance} if guidance else {}),
            "isMock": False,
        }
