"""Combine OCR's per-field evidence (app/ocr_retriever.py) with the visual
retriever's slug evidence (app/retriever.py) into one resolved wine slug.
Neither producer resolves a wine itself — this is the one place that does,
and the one place with a pass/fail confidence threshold, per the
requirement that ranking either falls honestly or is confident it got the
right card — no in-between status here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Wine
from .field_vocabulary import _field_values
from .label_fields import RetrievalFields
from .ocr import extract_year


# Placeholder, sums to 1.0 — uncalibrated, same caveat as retriever.py's
# SIFT_WEIGHT=0.45 comment: revisit once there's a labelled photo set to
# tune against. `abv` is deliberately absent: catalog.Wine has no ABV
# column, so there is nothing to match it against — it stays in
# RetrievalFields purely as informational OCR output.
FIELD_WEIGHTS = {
    "name": 0.30, "winery": 0.20, "slug": 0.20, "grape_varieties": 0.12,
    "year": 0.08, "region": 0.04, "category": 0.03, "color": 0.03,
}

# Placeholder — the parameter below which ranking honestly returns
# not_found, and above which it is confident about the resolved slug.
# Calibrated against the 6 real fixtures in tests/fixtures/ after fixing
# field_vocabulary.py's coverage bug (2026-09-23): 0.5 rejected a correct
# match at 0.4976 (balaklava-muskat, OCR only read 3/4 of the name) while
# the one genuinely ambiguous case (near-duplicate sibling wines, see
# thoughts/groom/2b_RETRIEVER.md) sits at 0.32 — well clear on either
# side of 0.45. Still a 6-photo sample; revisit once there's a bigger
# labelled set.
MATCH_THRESHOLD = 0.45


@dataclass(frozen=True)
class RankingResult:
    status: str  # "matched" | "not_found"
    slug: str | None
    score: float
    evidence: dict[str, float]  # every catalog slug's score, for inspection


def _actual_values(wine: Wine, field: str) -> set[str]:
    if field == "slug":
        return {wine.slug}
    if field == "year":
        year = extract_year(wine.name)
        return {str(year)} if year is not None else set()
    return set(_field_values(wine, field))


@dataclass(frozen=True)
class FieldContribution:
    field: str
    weight: float
    score: float  # best candidate score matching this wine's value, 0 when none match


def field_breakdown(wine: Wine, ocr_fields: RetrievalFields,
                    visual_fields: RetrievalFields) -> tuple[FieldContribution, ...]:
    """Per-field terms of the wine's score. Fields with no evidence at all are
    left out: they neither add to nor dilute the weighted average."""
    contributions = []
    for field, weight in FIELD_WEIGHTS.items():
        candidates = visual_fields.slug if field == "slug" else getattr(ocr_fields, field)
        if not candidates:
            continue
        actual = _actual_values(wine, field)
        best = max((candidate.score for candidate in candidates if candidate.value in actual), default=0.0)
        contributions.append(FieldContribution(field, weight, best))
    return tuple(contributions)


def _wine_score(wine: Wine, ocr_fields: RetrievalFields, visual_fields: RetrievalFields) -> float:
    contributions = field_breakdown(wine, ocr_fields, visual_fields)
    total_weight = sum(item.weight for item in contributions)
    total_score = sum(item.weight * item.score for item in contributions)
    return total_score / total_weight if total_weight else 0.0


def rank(ocr_fields: RetrievalFields, visual_fields: RetrievalFields, wines: list[Wine],
         *, threshold: float = MATCH_THRESHOLD) -> RankingResult:
    evidence = {wine.slug: round(_wine_score(wine, ocr_fields, visual_fields), 4) for wine in wines}
    if not evidence:
        return RankingResult("not_found", None, 0.0, evidence)
    slug, score = max(evidence.items(), key=lambda item: item[1])
    if score > threshold:
        return RankingResult("matched", slug, score, evidence)
    return RankingResult("not_found", None, score, evidence)
