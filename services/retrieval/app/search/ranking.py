"""Combine OCR's per-field evidence (app/ocr/retriever.py) with the visual
retriever's slug evidence (app/visual/retriever.py) into one resolved wine
slug. Neither producer resolves a wine itself — this is the one place that
does, and the one place that decides between an honest not_found and a match.

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

Because fields only add, a visual leader the label plainly contradicts
still wins on the visual weight alone. So before deciding, the top of the
ranking is checked against what OCR read (verify_shortlist in
search/verification.py): a wine is rejected when the label shows a
distinctive word of a rival's name that its own name lacks, or a
category/year that differs from its own. Rejected wines drop below the
rest; scores stay as they are.

The decision is the gap between the first and second wine (TZ: «отрыв
между 1-м и 2-м результатом»), not an absolute score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

from ..catalog.models import Wine
from ..evidence import FieldCandidate, RetrievalFields
from ..label_text.vintage import extract_year
from .verification import LabelCheck, generic_winery_tokens, verify_shortlist


FIELD_WEIGHTS = {
    "slug": 0.70, "name": 0.20, "winery": 0.20, "grape_varieties": 0.12,
    "year": 0.08, "region": 0.04, "category": 0.03,
}
TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())

VISUAL_TEMPERATURE = 0.05
OCR_TEMPERATURE = 0.06

MIN_MARGIN = 0.03

VISUAL_IDENTIFY_MIN = 0.25
CONFIRMING_FIELDS = ("year",)

VERIFY_SHORTLIST = 3
VERIFY_LIMIT = 8

HARD_CONTRADICTIONS = ("winery", "category", "year", "sweetness")


@dataclass(frozen=True)
class RankingResult:
    status: str
    slug: str | None
    score: float
    margin: float
    evidence: dict[str, float]
    rejected: dict[str, str] = field(default_factory=dict)
    checks: tuple[LabelCheck, ...] = ()

    def ranked(self, limit: int) -> list[tuple[str, float]]:
        return _ranked(self.evidence, limit, self.rejected)


def _ranked(evidence: dict[str, float], limit: int,
            rejected: dict[str, str] | None = None) -> list[tuple[str, float]]:
    rejected = rejected or {}
    return sorted(evidence.items(), key=lambda item: (item[0] in rejected, -item[1], item[0]))[:limit]


@dataclass(frozen=True)
class FieldContribution:
    field: str
    weight: float
    score: float


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
    terms = tuple(
        FieldContribution(field, FIELD_WEIGHTS[field],
                          max((distribution[value] for value in _actual_values(wine, field) if value in distribution),
                              default=0.0))
        for field, distribution in distributions.items()
    )
    if any(term.field == "name" and term.score > 0 for term in terms):
        return terms
    return tuple(FieldContribution(term.field, term.weight, 0.0) if term.field in CONFIRMING_FIELDS else term
                 for term in terms)


def field_breakdown(wine: Wine, ocr_fields: RetrievalFields,
                    visual_fields: RetrievalFields) -> tuple[FieldContribution, ...]:
    """Per-field terms of the wine's score, for fields that produced any
    candidates; weight × score / TOTAL_WEIGHT is each field's share."""
    return _contributions(wine, _distributions(ocr_fields, visual_fields))


def rank(ocr_fields: RetrievalFields, visual_fields: RetrievalFields, wines: list[Wine],
         *, min_margin: float = MIN_MARGIN, ocr_text: str = "") -> RankingResult:
    distributions = _distributions(ocr_fields, visual_fields)
    breakdowns = {wine.slug: _contributions(wine, distributions) for wine in wines}
    evidence = {slug: round(sum(term.weight * term.score for term in terms) / TOTAL_WEIGHT, 4)
                for slug, terms in breakdowns.items()}
    if not distributions or not evidence:
        return RankingResult("not_found", None, 0.0, 0.0, evidence)
    by_slug = {wine.slug: wine for wine in wines}
    order = [slug for slug, _ in _ranked(evidence, len(evidence))]
    shortlist = [by_slug[slug] for slug in order[:VERIFY_SHORTLIST]]
    named = {candidate.value for candidate in ocr_fields.name[:1]}
    shortlist += [wine for wine in wines if wine.name.strip() in named and wine not in shortlist]
    generic_winery = generic_winery_tokens(wines)
    while True:
        checks = verify_shortlist(shortlist, ocr_fields, ocr_text, generic_winery)
        slug, margin, rival = _decide(evidence, order, checks)
        if rival is None or rival in {wine.slug for wine in shortlist} or len(shortlist) >= VERIFY_LIMIT:
            break
        shortlist.append(by_slug[rival])
    rejected = {check.slug: check.reason for check in checks if check.kind}
    score = evidence[slug]
    if len(rejected) == len(checks):
        return RankingResult("not_found", None, score, margin, evidence, rejected, checks)
    is_identified = _is_identified(breakdowns[slug],
                                   next((c for c in checks if c.slug == slug), None) if ocr_text.strip() else None,
                                   _visual_share(visual_fields, slug, rejected))
    if is_identified and margin >= min_margin:
        return RankingResult("matched", slug, score, margin, evidence, rejected, checks)
    return RankingResult("not_found", None, score, margin, evidence, rejected, checks)


def _visual_share(visual_fields: RetrievalFields, slug: str, rejected: dict[str, str]) -> float:
    """The wine's share of the visual field among wines the label does not
    contradict: «Аврора 2024» next to a rejected «Аврора 2023» is the visual match."""
    candidates = tuple(c for c in visual_fields.slug if c.value not in rejected)
    return field_distribution(candidates, VISUAL_TEMPERATURE).get(slug, 0.0) if candidates else 0.0


def _is_identified(terms: tuple[FieldContribution, ...], check: LabelCheck | None, visual: float) -> bool:
    """A clear visual match (``visual`` — _visual_share) identifies a wine; a
    faint one only together with its name. OCR alone does only when the label shows every distinctive word
    of its name. «Пино Нуар полусухое» of one winery is every Pinot Noir
    label: read on a Табия bottle (not in the catalog), it must not match
    Новый Свет's wine of that name. Without label text (``check`` is None)
    there is nothing to check the name against."""
    name = next((term.score for term in terms if term.field == "name"), 0.0)
    if visual >= VISUAL_IDENTIFY_MIN or (visual > 0 and name > 0):
        return True
    return name > 0 and (check is None or check.is_fully_read)


def _decide(evidence: dict[str, float], order: list[str],
            checks: tuple[LabelCheck, ...]) -> tuple[str, float, str | None]:
    """The best checked wine the label does not contradict, its margin, and the runner-up.

    Out of the race: wines the label overturned (they outscored the winner),
    wines that contradict a stated fact, and — when the label spells out the
    winner's whole name — wines it contradicts by name. A name-contradicted
    wine below a winner the label names only in part stays a rival: the label
    may equally fit a sibling nobody checked («Цитрон» of «Пет-Нат
    Цитрон-Ркацители» fits «Петнат Цитрон – Рислинг» as well)."""
    by_slug = {check.slug: check for check in checks}
    winner = next((slug for slug in order if slug in by_slug and not by_slug[slug].kind), order[0])
    score = evidence[winner]
    fully_named = winner in by_slug and by_slug[winner].is_fully_read

    def is_out(slug: str) -> bool:
        check = by_slug.get(slug)
        if check is None or not check.kind:
            return False
        return evidence[slug] > score or check.kind in HARD_CONTRADICTIONS or fully_named

    rival = next((slug for slug in order if slug != winner and not is_out(slug)), None)
    return winner, (round(score - evidence[rival], 4) if rival else score), rival
