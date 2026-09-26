from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from ..label_fields import FieldCandidate, RetrievalFields
from ..sweetness import sugar_level
from .constants import (
    CLOSED_VOCABULARY_FIELDS,
    OCR_CROP_BOX,
    OCR_CROP_MIN_ASPECT,
    OCR_CROP_MIN_SIDE,
    OCR_CROP_MIN_WORDS,
    RANKING_CANDIDATES,
    WINERY_SHARED_FIELDS,
    WINERY_SPENDS_WORDS_AT,
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


class OcrRetriever:
    def __init__(self, vocabulary: FieldVocabulary) -> None:
        self.vocabulary = vocabulary

    def extract(self, image: np.ndarray) -> RetrievalFields:
        return self.trace(image).fields

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
        sweetness = sugar_level(text)
        return RetrievalFields(**fields, winery=winery,
                               year=extract_year_candidates(label.words),
                               abv=extract_abv_candidates(label.words),
                               sweetness=(FieldCandidate(sweetness, 1.0),) if sweetness else ())
