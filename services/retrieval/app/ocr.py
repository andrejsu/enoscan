from __future__ import annotations

from functools import lru_cache
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass

import numpy as np

from .label_fields import MAX_CANDIDATES, FieldCandidate
from .text_normalize import CYRILLIC_TO_LATIN


TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
VINTAGE_PATTERN = re.compile(r"(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)")
STOP_WORDS = frozenset({
    "beloe", "butylka", "etiketka", "igristoe", "krasnoe", "rozovoe", "suhoe",
    "vino", "wine", "winery",
})


ENGINE_NAME = "rapidocr-3.9 PP-OCRv5 cyrillic"

_LATIN_TO_CYRILLIC = str.maketrans("ABCEHKMOPTXYaceopxy", "АВСЕНКМОРТХУасеорху")
_HOMOGLYPHS = frozenset("ABCEHKMOPTXY")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_LETTER = r"[^\W\d_]"


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
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def search_text(self) -> str:
        return " ".join(word.text for word in self.words if word.confidence >= 40)


@lru_cache(maxsize=1)
def load_engine():
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    return RapidOCR(params={"Rec.lang_type": LangRec.CYRILLIC, "Rec.ocr_version": OCRVersion.PPOCRV5,
                            "Rec.model_type": ModelType.MOBILE, "Global.log_level": "error"})


def extract_label(image: np.ndarray) -> OcrResult:
    """One detected text line per OcrWord; bbox in ``image`` pixels."""
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
    for token in text.split():
        if _CYRILLIC.search(token):
            folded.append(_to_cyrillic(token))
            continue
        folded.append(token)
        letters = [c for c in token if c.isalpha()]
        if len(letters) >= 3 and token.isupper() and set(letters) <= _HOMOGLYPHS:
            folded.append(_to_cyrillic(token))
    return " ".join(folded)


def _to_cyrillic(token: str) -> str:
    token = token.translate(_LATIN_TO_CYRILLIC)
    if sum(c.isdigit() for c in token) == 1:  # "3АКАТ" → "ЗАКАТ", never "2023г"
        token = re.sub(rf"(?<={_LETTER})3|3(?={_LETTER})", "З", token)
    return token


def extract_year(text: str) -> int | None:
    found = {int(match) for match in VINTAGE_PATTERN.findall(text)}
    if len(found) != 1:
        return None
    return found.pop()


def _group_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    return list(lines.values())


def extract_year_candidates(words: list[OcrWord], *, limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
    best: dict[int, float] = {}
    for line in _group_lines(words):
        text = " ".join(w.text for w in line)
        confidence = min(w.confidence for w in line)
        if confidence < 60:
            continue
        if not re.search(r"урожа|vintage|harvest", text, re.I) or re.search(r"основан|since|founded|розлив|bottl", text, re.I):
            continue
        for value in {int(match) for match in VINTAGE_PATTERN.findall(text)}:
            best[value] = max(best.get(value, 0.0), confidence / 100)
    candidates = sorted(
        (FieldCandidate(str(value), round(score, 4)) for value, score in best.items()),
        key=lambda candidate: candidate.score, reverse=True,
    )
    return tuple(candidates[:limit])


def extract_abv_candidates(words: list[OcrWord], *, limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
    best: dict[float, float] = {}
    for line in _group_lines(words):
        text = " ".join(w.text for w in line)
        confidence = min(w.confidence for w in line)
        if confidence < 60:
            continue
        for match in re.finditer(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*(?:%|об\.?\b)|\balc\.?\s*(\d{1,2}(?:[.,]\d)?)(?![\d.,])", text, re.I):
            value = float((match.group(1) or match.group(2)).replace(",", "."))
            if 1 <= value <= 30:
                best[value] = max(best.get(value, 0.0), confidence / 100)
    candidates = sorted(
        (FieldCandidate(str(value), round(score, 4)) for value, score in best.items()),
        key=lambda candidate: candidate.score, reverse=True,
    )
    return tuple(candidates[:limit])


PHONETIC_RULES = tuple((re.compile(pattern), replacement) for pattern, replacement in (
    (r"eau", "o"), (r"ch", "sh"), (r"oi", "ua"), (r"ou", "u"), (r"au", "o"), (r"ai", "e"), (r"gn", "n"),
    (r"ie", "i"), (r"ay$", "e"), (r"(?<=n)c$", ""), (r"(?<=[eo])[tdx]$", ""),
    (r"(?<=[aeiou])s(?=[aeiou])", "z"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"q", "k"), (r"w", "v"),
    (r"x", "ks"), (r"y", "i"), (r"(.)\1", r"\1"), (r"(?<=[^aeiou])e$", ""),
))
_LATIN_ACCENTS = str.maketrans("àâäáéèêëíîïóôöúûüùçñ", "aaaaeeeeiiiooouuuucn")


def phonetic_key(token: str) -> str:
    for pattern, replacement in PHONETIC_RULES:
        token = pattern.sub(replacement, token)
    return token


def _raw_tokens(value: str) -> list[str]:
    normalized = (unicodedata.normalize("NFKC", value).casefold()
                  .translate(_LATIN_ACCENTS).translate(CYRILLIC_TO_LATIN))
    return TOKEN_PATTERN.findall(normalized)


def _tokens(value: str, *, stop_words: Collection[str] = STOP_WORDS,
            aliases: dict[str, str] | None = None) -> set[str]:
    tokens = set()
    for raw in _raw_tokens(value):
        if len(raw) < 3 or raw in stop_words:
            continue
        token = phonetic_key(raw)
        token = aliases.get(token, token) if aliases else token
        if len(token) >= 3:
            tokens.add(token)
    return tokens
