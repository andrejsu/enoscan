from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

import numpy as np

from .constants import HOMOGLYPH_MIN_LETTERS, SEARCH_TEXT_MIN_CONFIDENCE


ENGINE_NAME = "rapidocr-3.9 PP-OCRv5 cyrillic"

_LATIN_TO_CYRILLIC = str.maketrans("ABCEHKMOPTXYaceopxyu", "АВСЕНКМОРТХУасеорхуи")
# The Cyrillic recognizer sometimes emits Greek letters: «ΟΛΕΓ» is «ОЛЕГ».
_GREEK_TO_CYRILLIC = str.maketrans("ΑΒΓΔΕΖΗΚΛΜΟΠΡΤΥΦΧαγδεικλμοπρτυφχ", "АВГДЕЗНКЛМОПРТУФХагдеиклмопртуфх")
_HOMOGLYPHS = frozenset("ABCEHKMOPTXY")
_MIXED_HOMOGLYPHS = _HOMOGLYPHS | frozenset("aceopxyu")
_DIGIT_LETTERS = str.maketrans("63", "бз")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_THREE_NEXT_TO_LETTER = re.compile(r"(?<=[^\W\d_])3|3(?=[^\W\d_])")


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    line: tuple[int, int, int]


@dataclass(frozen=True)
class OcrResult:
    words: tuple[OcrWord, ...] = ()

    @property
    def search_text(self) -> str:
        return " ".join(word.text for word in self.words if word.confidence >= SEARCH_TEXT_MIN_CONFIDENCE)


@lru_cache(maxsize=1)
def load_engine():
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    return RapidOCR(params={"Rec.lang_type": LangRec.CYRILLIC, "Rec.ocr_version": OCRVersion.PPOCRV5,
                            "Rec.model_type": ModelType.MOBILE, "Global.log_level": "error"})


def extract_label(image: np.ndarray) -> OcrResult:
    result = load_engine()(image)
    words = []
    for index, (box, text, score) in enumerate(zip(result.boxes if result.boxes is not None else (),
                                                   result.txts or (), result.scores or ())):
        text = fold_homoglyphs(text.strip())
        if not text:
            continue
        xs, ys = [point[0] for point in box], [point[1] for point in box]
        bbox = (round(min(xs)), round(min(ys)), round(max(xs) - min(xs)), round(max(ys) - min(ys)))
        words.append(OcrWord(text, round(float(score) * 100, 1), bbox, (1, 1, index + 1)))
    return OcrResult(tuple(words))


def fold_homoglyphs(text: str) -> str:
    folded = []
    for token in text.translate(_GREEK_TO_CYRILLIC).split():
        if _CYRILLIC.search(token):
            folded.append(_to_cyrillic(token))
            continue
        folded.append(token)
        letters = [c for c in token if c.isalpha()]
        if len(letters) < HOMOGLYPH_MIN_LETTERS:
            continue
        if token.isupper() and set(letters) <= _HOMOGLYPHS:
            folded.append(_to_cyrillic(token))
        elif token.isupper() and "U" in token:
            # Serif capitals: «UUA UALLIS» is «UVA VALLIS».
            folded.append(token.replace("U", "V"))
        elif any(c in "63" for c in token) and set(letters) <= _MIXED_HOMOGLYPHS:
            # «Py6uH» is «Рубин» with a б read as 6.
            folded.append(token.translate(_LATIN_TO_CYRILLIC).translate(_DIGIT_LETTERS))
    return " ".join(folded)


def _to_cyrillic(token: str) -> str:
    token = token.translate(_LATIN_TO_CYRILLIC)
    if sum(c.isdigit() for c in token) == 1:
        token = _THREE_NEXT_TO_LETTER.sub("З", token)
    return token
