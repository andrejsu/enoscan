from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from ..evidence import FieldCandidate, RetrievalFields
from ..label_text.sweetness import sugar_level
from .constants import (
    CLOSED_VOCABULARY_FIELDS,
    OCR_CROP_BOX,
    OCR_CROP_MIN_ASPECT,
    OCR_CROP_MIN_SIDE,
    OCR_CROP_MIN_WORDS,
    RANKING_CANDIDATES,
    WINERY_SHARED_FIELDS,
    WINERY_SPENDS_WORDS_AT,
    OTHER_WINERY_NAME_FACTOR,
)
from .engine import OcrResult, extract_label
from .fields import extract_abv_candidates, extract_year_candidates
from .vocabulary import FieldVocabulary


@dataclass(frozen=True)
class OcrTrace:
    fields: RetrievalFields
    label: OcrResult
    ocr_ms: int = 0
    passes: tuple[str, ...] = ("full",)


def ocr_crop_box(image: np.ndarray) -> tuple[float, float, float, float]:
    height, width = image.shape[:2]
    if min(height, width) < OCR_CROP_MIN_SIDE:
        return 0.0, 0.0, 1.0, 1.0
    left, top, right, bottom = OCR_CROP_BOX
    if width / height < OCR_CROP_MIN_ASPECT:
        left, right = 0.0, 1.0
    return left, top, right, bottom


def ocr_crop(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    left, top, right, bottom = ocr_crop_box(image)
    return image[int(top * height):int(bottom * height), int(left * width):int(right * width)]


def winery_first_names(own: tuple[FieldCandidate, ...],
                       catalog: tuple[FieldCandidate, ...]) -> tuple[FieldCandidate, ...]:
    """Name candidates once OCR has read the winery: the best of its own names
    scores 1.0 (they compete only with each other), the rest of the catalog at
    OTHER_WINERY_NAME_FACTOR. «ДЕНИСОВ … Совинон» is Denisov's «Совиньон Блан»
    before it is «AGORA Совиньон», which spells the read word out in full."""
    best: dict[str, float] = {}
    top = max((candidate.score for candidate in own), default=0.0)
    for candidate in own:
        best[candidate.value] = round(candidate.score / top, 4)
    for candidate in catalog:
        score = round(candidate.score * OTHER_WINERY_NAME_FACTOR, 4)
        best[candidate.value] = max(best.get(candidate.value, 0.0), score)
    ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))[:RANKING_CANDIDATES]
    return tuple(FieldCandidate(value, score) for value, score in ranked)


class OcrRetriever:
    def __init__(self, vocabulary: FieldVocabulary) -> None:
        self.vocabulary = vocabulary

    def trace(self, image: np.ndarray) -> OcrTrace:
        started = time.perf_counter()
        if ocr_crop_box(image) == (0.0, 0.0, 1.0, 1.0):
            label, passes = extract_label(image), ("full",)
        else:
            label, passes = extract_label(ocr_crop(image)), ("crop",)
        if passes == ("crop",) and len(label.words) < OCR_CROP_MIN_WORDS:
            label, passes = extract_label(image), ("crop", "full")
        fields = self._fields(label)
        return OcrTrace(fields, label, ocr_ms=round((time.perf_counter() - started) * 1000), passes=passes)

    def _fields(self, label: OcrResult) -> RetrievalFields:
        text = label.search_text
        winery = self.vocabulary.top("winery", text, limit=RANKING_CANDIDATES)
        spent = (self.vocabulary.explained("winery", text, winery[0].value)
                 if winery and winery[0].score >= WINERY_SPENDS_WORDS_AT else set())
        fields = {field: self.vocabulary.top(field, text, limit=RANKING_CANDIDATES,
                                             ignore=spent if field in WINERY_SHARED_FIELDS else ())
                  for field in CLOSED_VOCABULARY_FIELDS if field != "winery"}
        if spent:
            fields["name"] = winery_first_names(
                self.vocabulary.winery_names(winery[0].value, text, limit=RANKING_CANDIDATES, ignore=spent),
                fields["name"])
        sweetness = sugar_level(text)
        return RetrievalFields(**fields, winery=winery,
                               year=extract_year_candidates(label.words),
                               abv=extract_abv_candidates(label.words),
                               sweetness=(FieldCandidate(sweetness, 1.0),) if sweetness else ())
