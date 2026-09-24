from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from .field_vocabulary import CLOSED_VOCABULARY_FIELDS, FieldVocabulary
from .label_fields import RetrievalFields
from .ocr import OcrResult, OcrWord, extract_abv_candidates, extract_label, extract_year_candidates


WINERY_SPENDS_WORDS_AT = 0.5
WINERY_SHARED_FIELDS = ("name", "grape_varieties")
RANKING_CANDIDATES = 50


@dataclass(frozen=True)
class OcrTrace:
    """extract()'s result plus what OCR read, for the scan debug panel."""
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
        fields = self._fields(label.words)
        return OcrTrace(fields, label, ocr_ms=round((time.perf_counter() - started) * 1000))

    def _fields(self, words: tuple[OcrWord, ...]) -> RetrievalFields:
        text = " ".join(word.text for word in words if word.confidence >= 40)
        winery = self.vocabulary.top("winery", text, limit=RANKING_CANDIDATES)
        spent = (self.vocabulary.explained("winery", text, winery[0].value)
                 if winery and winery[0].score >= WINERY_SPENDS_WORDS_AT else set())
        fields = {field: self.vocabulary.top(field, text, limit=RANKING_CANDIDATES,
                                             ignore=spent if field in WINERY_SHARED_FIELDS else ())
                  for field in CLOSED_VOCABULARY_FIELDS if field != "winery"}
        fields["winery"] = winery
        fields["year"] = extract_year_candidates(words)
        fields["abv"] = extract_abv_candidates(words)
        return RetrievalFields(**fields)
