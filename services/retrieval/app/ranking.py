"""Combine OCR's per-field evidence (app/ocr/retriever.py) with the visual
retriever's slug evidence (app/retriever.py) into one resolved wine slug.
Neither producer resolves a wine itself — this is the one place that does,
and the one place that decides between an honest not_found and a match.

Raw producer scores are not comparable across fields: OCR's name scores
shrink as the label gets noisier (a clear winner can sit at 0.28), and a
wine used to collect credit from whichever of 50 candidates happened to
match it. So each field is first turned into a distribution over its own
candidates — the field's top-1 carries most of the mass, near-ties share
it, low-ranked candidates get almost none. A field that can't tell
candidates apart then can't reorder them.

Fields only ever add support: a wine's score is the weighted sum of its
per-field probabilities over the fixed total of FIELD_WEIGHTS, so a field
that agrees raises the score, and a field that has no opinion about this
wine adds nothing instead of dragging the others down. The score reads as
"share of the full support a wine could get", and a clear match that both
the retriever and OCR back sits around 0.4-0.8.

The decision is the gap between the first and second wine (TZ: «отрыв
между 1-м и 2-м результатом»), not an absolute score.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from .catalog import Wine
from .label_fields import FieldCandidate, RetrievalFields
from .ocr.fields import extract_year


# Relative importance; scores are divided by their fixed sum. Absent on
# purpose: `abv` — catalog.Wine has no ABV column to match; `color` — the
# catalog's color is free-text tasting notes («Нежный лососевый цвет…»),
# so OCR matches against it are noise that never hit the right wine.
# Tuned 2026-09-25 on 156 queries (9 real photos + 147 hard augmentations of
# catalog images, see scripts/README.md); held on both halves of the set.
# Still a small sample — revisit with more real photos.
FIELD_WEIGHTS = {
    "slug": 0.70, "name": 0.20, "winery": 0.20, "grape_varieties": 0.12,
    "year": 0.08, "region": 0.04, "category": 0.03,
}
TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())

# Softmax temperature per source, in raw-score units: how far below the
# field's top-1 a candidate may sit and still share its probability.
# Visual scores bunch within ~0.1 of each other, OCR ones spread wider.
VISUAL_TEMPERATURE = 0.05
OCR_TEMPERATURE = 0.06

# Minimum top-1 minus top-2 score for `matched`. On the tuning set 0.06 gave
# precision 0.94 at recall 0.64 (the old absolute 0.45 threshold: 0.86 at
# 0.62); on real photos 0.04-0.06 was a plateau, 0.08 already lost matches.
MIN_MARGIN = 0.06

# Fields that can pin down one wine. The rest (winery, grape, category,
# color, region, year) are shared by many wines: OCR reading only
# "Красное" must never match whichever red wine comes first. Those fields
# may still rank, never match alone.
IDENTIFYING_FIELDS = ("name", "slug")


@dataclass(frozen=True)
class RankingResult:
    status: str  # "matched" | "not_found"
    slug: str | None  # set only when matched
    score: float  # top-1 wine's score, whether or not it matched
    margin: float  # top-1 minus top-2 score
    evidence: dict[str, float]  # every catalog slug's score, for inspection

    def ranked(self, limit: int) -> list[tuple[str, float]]:
        return _ranked(self.evidence, limit)


def _ranked(evidence: dict[str, float], limit: int) -> list[tuple[str, float]]:
    # Slug breaks score ties, so equal evidence never depends on catalog order.
    return sorted(evidence.items(), key=lambda item: (-item[1], item[0]))[:limit]


@dataclass(frozen=True)
class FieldContribution:
    field: str
    weight: float
    score: float  # this wine's probability within the field, 0 when absent


def _actual_values(wine: Wine, field: str) -> set[str]:
    if field == "slug":
        return {wine.slug}
    if field == "year":
        year = extract_year(wine.name)
        return {str(year)} if year is not None else set()
    return set(wine.field_values(field))


def field_distribution(candidates: tuple[FieldCandidate, ...], temperature: float) -> dict[str, float]:
    """Softmax over one field's candidates, relative to its own top-1."""
    top = max(candidate.score for candidate in candidates)
    weights: dict[str, float] = {}
    for candidate in candidates:
        weight = exp((candidate.score - top) / temperature)
        weights[candidate.value] = max(weights.get(candidate.value, 0.0), weight)
    total = sum(weights.values())
    return {value: weight / total for value, weight in weights.items()}


def _distributions(ocr_fields: RetrievalFields, visual_fields: RetrievalFields) -> dict[str, dict[str, float]]:
    distributions = {}
    for field in FIELD_WEIGHTS:
        candidates = visual_fields.slug if field == "slug" else getattr(ocr_fields, field)
        if candidates:
            temperature = VISUAL_TEMPERATURE if field == "slug" else OCR_TEMPERATURE
            distributions[field] = field_distribution(candidates, temperature)
    return distributions


def _contributions(wine: Wine, distributions: dict[str, dict[str, float]]) -> tuple[FieldContribution, ...]:
    return tuple(
        FieldContribution(field, FIELD_WEIGHTS[field],
                          max((distribution[value] for value in _actual_values(wine, field) if value in distribution),
                              default=0.0))
        for field, distribution in distributions.items()
    )


def field_breakdown(wine: Wine, ocr_fields: RetrievalFields,
                    visual_fields: RetrievalFields) -> tuple[FieldContribution, ...]:
    """Per-field terms of the wine's score, for fields that produced any
    candidates; weight × score / TOTAL_WEIGHT is each field's share."""
    return _contributions(wine, _distributions(ocr_fields, visual_fields))


def _score(contributions: tuple[FieldContribution, ...]) -> float:
    return sum(item.weight * item.score for item in contributions) / TOTAL_WEIGHT


def rank(ocr_fields: RetrievalFields, visual_fields: RetrievalFields, wines: list[Wine],
         *, min_margin: float = MIN_MARGIN) -> RankingResult:
    distributions = _distributions(ocr_fields, visual_fields)
    breakdowns = {wine.slug: _contributions(wine, distributions) for wine in wines}
    evidence = {slug: round(_score(terms), 4) for slug, terms in breakdowns.items()}
    if not distributions or not evidence:
        return RankingResult("not_found", None, 0.0, 0.0, evidence)
    ranked = _ranked(evidence, 2)
    slug, score = ranked[0]
    margin = round(score - ranked[1][1], 4) if len(ranked) > 1 else score
    is_identified = any(term.field in IDENTIFYING_FIELDS and term.score > 0 for term in breakdowns[slug])
    if is_identified and margin >= min_margin:
        return RankingResult("matched", slug, score, margin, evidence)
    return RankingResult("not_found", None, score, margin, evidence)
