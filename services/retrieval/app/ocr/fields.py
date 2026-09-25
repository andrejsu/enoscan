from __future__ import annotations

from collections.abc import Callable, Iterable
import re

from ..label_fields import MAX_CANDIDATES, FieldCandidate
from .constants import ABV_MAX, ABV_MIN, FIELD_LINE_MIN_CONFIDENCE
from .engine import OcrWord


# A year inside a date or a standard number ("15.03.2024", "ГОСТ 32030-2013") is not a vintage.
_VINTAGE = re.compile(r"(?<![\d./-])(19[5-9]\d|20[0-2]\d)(?![\d]|[./-]\d)")
_VINTAGE_CONTEXT = re.compile(r"урожа|vintage|harvest", re.IGNORECASE)
_NOT_VINTAGE_CONTEXT = re.compile(r"основан|since|founded|розлив|bottl|гост", re.IGNORECASE)
_ABV = re.compile(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*(?:%|об\.?\b)|\balc\.?\s*(\d{1,2}(?:[.,]\d)?)(?![\d.,])",
                  re.IGNORECASE)


def extract_year(text: str) -> int | None:
    found = {int(match) for match in _VINTAGE.findall(text)}
    return found.pop() if len(found) == 1 else None


def extract_year_candidates(words: Iterable[OcrWord], *,
                            limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
    """Years marked as a harvest win. Front labels usually print the vintage
    bare ("BRUT ROSE 2024"), so without a marked one the label's only
    unmarked year is taken; two unmarked years stay ambiguous."""
    words = list(words)
    marked = _line_candidates(words, _line_years, limit)
    if marked:
        return marked
    unmarked = _line_candidates(words, _unmarked_years, limit)
    return unmarked if len(unmarked) == 1 else ()


def extract_abv_candidates(words: Iterable[OcrWord], *,
                           limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
    return _line_candidates(words, _line_abvs, limit)


def _line_years(text: str) -> set[int]:
    if not _VINTAGE_CONTEXT.search(text) or _NOT_VINTAGE_CONTEXT.search(text):
        return set()
    return {int(match) for match in _VINTAGE.findall(text)}


def _unmarked_years(text: str) -> set[int]:
    return set() if _NOT_VINTAGE_CONTEXT.search(text) else {int(match) for match in _VINTAGE.findall(text)}


def _line_abvs(text: str) -> list[float]:
    values = (float((match.group(1) or match.group(2)).replace(",", ".")) for match in _ABV.finditer(text))
    return [value for value in values if ABV_MIN <= value <= ABV_MAX]


def _line_candidates(words: Iterable[OcrWord], values_of: Callable[[str], Iterable[object]],
                     limit: int) -> tuple[FieldCandidate, ...]:
    best: dict[object, float] = {}
    for line in _group_lines(words):
        confidence = min(word.confidence for word in line)
        if confidence < FIELD_LINE_MIN_CONFIDENCE:
            continue
        for value in values_of(" ".join(word.text for word in line)):
            best[value] = max(best.get(value, 0.0), confidence / 100)
    candidates = sorted(
        (FieldCandidate(str(value), round(score, 4)) for value, score in best.items()),
        key=lambda candidate: candidate.score, reverse=True,
    )
    return tuple(candidates[:limit])


def _group_lines(words: Iterable[OcrWord]) -> list[list[OcrWord]]:
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    return list(lines.values())
