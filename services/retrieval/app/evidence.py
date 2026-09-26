"""Shared evidence struct for the OCR block and the visual retriever.

Both sources speak this one shape so a downstream ranking stage can combine
them without per-source conversions. See app/ocr/retriever.py (fills the
text fields), app/search/service.py (fills `slug` from the visual retriever)
and app/search/ranking.py (does the actual wine lookup) — neither producer
invents its own candidate shape or its own notion of "confidence": every
score here is normalized to [0, 1] and follows the same criteria documented
on each producer.
"""

from __future__ import annotations

from dataclasses import dataclass


TEXT_FIELDS = ("name", "winery", "year", "grape_varieties", "abv", "category", "sweetness", "region")

MAX_CANDIDATES = 10


@dataclass(frozen=True)
class FieldCandidate:
    value: str
    score: float


@dataclass(frozen=True)
class RetrievalFields:
    name: tuple[FieldCandidate, ...] = ()
    winery: tuple[FieldCandidate, ...] = ()
    grape_varieties: tuple[FieldCandidate, ...] = ()
    year: tuple[FieldCandidate, ...] = ()
    abv: tuple[FieldCandidate, ...] = ()
    category: tuple[FieldCandidate, ...] = ()
    sweetness: tuple[FieldCandidate, ...] = ()
    region: tuple[FieldCandidate, ...] = ()
    slug: tuple[FieldCandidate, ...] = ()


def fields_from_json(payload: dict) -> RetrievalFields:
    """Inverse of dataclasses.asdict(RetrievalFields) — how the OCR service
    (app/ocr/api.py) sends fields to ranking. Unknown keys are ignored."""
    return RetrievalFields(**{
        field: tuple(FieldCandidate(str(item["value"]), float(item["score"])) for item in payload[field])
        for field in RetrievalFields.__dataclass_fields__ if field in payload
    })
