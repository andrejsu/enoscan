from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from ..label_fields import RetrievalFields
from .constants import CLOSED_VOCABULARY_FIELDS, RANKING_CANDIDATES, WINERY_SHARED_FIELDS, WINERY_SPENDS_WORDS_AT
from .engine import OcrResult, extract_label
from .fields import extract_abv_candidates, extract_year_candidates
from .vocabulary import FieldVocabulary


@dataclass(frozen=True)
class OcrTrace:
    fields: RetrievalFields
    label: OcrResult
    ocr_ms: int = 0


class OcrRetriever:
    def __init__(self, vocabulary: FieldVocabulary) -> None:
        self.vocabulary = vocabulary

    def extract(self, image: np.ndarray) -> RetrievalFields:
        return self.trace(image).fields

    def trace(self, image: np.ndarray) -> OcrTrace:
        started = time.perf_counter()
        label = extract_label(image)
        fields = self._fields(label)
        return OcrTrace(fields, label, ocr_ms=round((time.perf_counter() - started) * 1000))

    def _fields(self, label: OcrResult) -> RetrievalFields:
        text = label.search_text
        winery = self.vocabulary.top("winery", text, limit=RANKING_CANDIDATES)
        spent = (self.vocabulary.explained("winery", text, winery[0].value)
                 if winery and winery[0].score >= WINERY_SPENDS_WORDS_AT else set())
        fields = {field: self.vocabulary.top(field, text, limit=RANKING_CANDIDATES,
                                             ignore=spent if field in WINERY_SHARED_FIELDS else ())
                  for field in CLOSED_VOCABULARY_FIELDS if field != "winery"}
        return RetrievalFields(**fields, winery=winery,
                               year=extract_year_candidates(label.words),
                               abv=extract_abv_candidates(label.words))
