"""OCR-driven field extraction — standalone, detached from the main scanner
(app/service.py, app/main.py, which this module never imports and never
affects). Reuses app/ocr.py's label reading exactly as-is; the only thing
this module adds is turning OCR's raw findings into app/label_fields.py's
RetrievalFields — ranked candidates per field, scored by the criteria
documented there. It never resolves a wine/slug itself; that is
app/ranking.py's job.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from .field_vocabulary import CLOSED_VOCABULARY_FIELDS, FieldVocabulary
from .label_fields import RetrievalFields
from .label_normalize import Config as LabelConfig, PreparedQuery, Segmenter, prepare_query
from .ocr import OcrResult, OcrWord, extract_abv_candidates, extract_label, extract_year_candidates


@dataclass(frozen=True)
class OcrTrace:
    """extract()'s result plus the intermediate state behind it, for the
    scan debug panel (app/scan_debug.py)."""
    fields: RetrievalFields
    prepared: PreparedQuery
    labels: tuple[OcrResult, ...]  # one per Tesseract pass: crop, then full frame (deep only)
    prepare_ms: int = 0
    ocr_ms: int = 0


class OcrRetriever:
    def __init__(self, vocabulary: FieldVocabulary, *, ocr_options: dict | None = None,
                 segmenter: Segmenter | None = None, label_config: LabelConfig | None = None,
                 use_sam: bool = False) -> None:
        self.vocabulary = vocabulary
        self.ocr_options = ocr_options or {}
        self.segmenter = segmenter
        self.label_config = label_config or LabelConfig()
        self.use_sam = use_sam

    def extract(self, image: np.ndarray) -> RetrievalFields:
        return self.trace(image).fields

    def extract_deep(self, image: np.ndarray) -> RetrievalFields:
        return self.trace(image, deep=True).fields

    def trace(self, image: np.ndarray, *, deep: bool = False) -> OcrTrace:
        """``deep=False`` is extract(). ``deep=True`` is extract_deep(): a
        second OCR pass over the raw, uncropped image, merged in. The crop's fixed "lower-middle third" heuristic
        (label_normalize._fast_crop) sometimes cuts the one word that would
        identify the wine even when it reads everything else around it
        cleanly — e.g. a label crop read "БЕЛОЕ СУХО 2024 №4" fine but
        missed "Алиготе" a few hundred px outside the crop, on a photo
        where two near-identical sibling wines differ only by that word.
        Costs one more Tesseract call, so this is reserved for cases worth
        double-checking (see app/ranking_main.py's borderline retry), not
        run on every request.

        Both modes use the same normalization entrypoint the visual retriever
        uses (scripts/label_prep.py), instead of handing ocr.extract_label()
        the raw upload directly."""
        started = time.perf_counter()
        prepared = prepare_query(image, segmenter=self.segmenter, config=self.label_config,
                                 fast=not self.use_sam)
        prepared_at = time.perf_counter()
        labels = [extract_label(prepared.ocr, **self.ocr_options)]
        if deep:
            labels.append(extract_label(image, **self.ocr_options))
        words = tuple(word for label in labels for word in label.words)
        fields = self._fields(words)
        finished = time.perf_counter()
        return OcrTrace(fields, prepared, tuple(labels),
                        prepare_ms=round((prepared_at - started) * 1000),
                        ocr_ms=round((finished - prepared_at) * 1000))

    def _fields(self, words: tuple[OcrWord, ...]) -> RetrievalFields:
        text = " ".join(word.text for word in words if word.confidence >= 40)
        fields = {field: self.vocabulary.top(field, text) for field in CLOSED_VOCABULARY_FIELDS}
        fields["year"] = extract_year_candidates(words)
        fields["abv"] = extract_abv_candidates(words)
        return RetrievalFields(**fields)
