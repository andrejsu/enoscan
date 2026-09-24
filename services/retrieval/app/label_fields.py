"""Shared evidence struct for the OCR block and the visual retriever.

Both sources speak this one shape so a downstream ranking stage can combine
them without per-source conversions. See app/ocr/retriever.py (fills the
text fields) and app/ranking.py (fills `slug` from the visual retriever and
does the actual wine lookup) — neither invents its own candidate shape or
its own notion of "confidence": every score here is normalized to [0, 1]
and follows the same criteria documented on each producer.
"""

from __future__ import annotations

from dataclasses import dataclass


# `year`/`abv` are OCR-only: they read off the label directly and have no
# column on catalog.Wine. Everything else mirrors an existing Wine field.
REQUIRED_FIELDS = ("name", "winery")
OPTIONAL_FIELDS = ("year", "grape_varieties", "abv", "category", "color", "region")
TEXT_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

MAX_CANDIDATES = 10


@dataclass(frozen=True)
class FieldCandidate:
    value: str  # year/abv are also stringified, so every field shares one type
    score: float  # 0..1, comparable across every field and every source


@dataclass(frozen=True)
class RetrievalFields:
    name: tuple[FieldCandidate, ...] = ()
    winery: tuple[FieldCandidate, ...] = ()
    grape_varieties: tuple[FieldCandidate, ...] = ()
    year: tuple[FieldCandidate, ...] = ()
    abv: tuple[FieldCandidate, ...] = ()
    category: tuple[FieldCandidate, ...] = ()
    color: tuple[FieldCandidate, ...] = ()
    region: tuple[FieldCandidate, ...] = ()
    slug: tuple[FieldCandidate, ...] = ()  # visual-retriever-only field


def fields_from_json(payload: dict) -> RetrievalFields:
    """Inverse of dataclasses.asdict(RetrievalFields) — how the OCR service
    (app/ocr/main.py) sends fields to ranking. Unknown keys are ignored."""
    return RetrievalFields(**{
        field: tuple(FieldCandidate(str(item["value"]), float(item["score"])) for item in payload[field])
        for field in RetrievalFields.__dataclass_fields__ if field in payload
    })
