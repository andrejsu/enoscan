from __future__ import annotations

import re
import unicodedata
import time
from collections.abc import Collection
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

from .catalog import Wine
from .label_fields import MAX_CANDIDATES, FieldCandidate
from .text_normalize import CYRILLIC_TO_LATIN, token_similarity as _token_similarity


TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
VINTAGE_PATTERN = re.compile(r"(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)")
STOP_WORDS = frozenset({
    "beloe", "butylka", "etiketka", "igristoe", "krasnoe", "rozovoe", "suhoe",
    "vino", "wine", "winery",
})


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    line: tuple[int, int, int]


@dataclass(frozen=True)
class LabelField:
    value: int | float
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float
    reason: str


@dataclass(frozen=True)
class OcrResult:
    words: tuple[OcrWord, ...] = ()
    year: LabelField | None = None
    abv: LabelField | None = None
    error: str | None = None
    passes: int = 1

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def search_text(self) -> str:
        return " ".join(word.text for word in self.words if word.confidence >= 40)


def extract_label(image: np.ndarray, *, timeout: float = 2.0, psm: int = 6,
                  preprocess: bool = True, retry: bool = False) -> OcrResult:
    started = time.perf_counter()
    height, width = image.shape[:2]
    scale = min(1.0, 1400 / max(height, width))
    original = image
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if preprocess:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(image)
    else:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    remaining = timeout - (time.perf_counter() - started)
    if remaining <= 0:
        return OcrResult(error="timeout", passes=0)
    words, error = _read_words(image, remaining, psm, scale)
    passes = 1
    # Optional experiment: retry at most one doubtful numeric line, within the same budget.
    if retry and not error:
        doubtful = next((w for w in words if any(c.isdigit() for c in w.text) and w.confidence < 60), None)
        remaining = timeout - (time.perf_counter() - started)
        if doubtful and remaining > 0.2:
            line_words = [w for w in words if w.line == doubtful.line]
            x, y, w, h = _bounds(line_words)
            x0, y0 = max(0, x - 8), max(0, y - 8)
            crop = original[y0:min(height, y + h + 8), x0:min(width, x + w + 8)]
            crop = cv2.cvtColor(cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB)
            revised, retry_error = _read_words(crop, remaining, 7, 2.0, (x0, y0), doubtful.line)
            passes += 1
            if revised and np.mean([w.confidence for w in revised]) > np.mean([w.confidence for w in line_words]):
                words = [w for w in words if w.line != doubtful.line] + revised
            error = retry_error
    year, abv = extract_fields(words)
    return OcrResult(tuple(words), year, abv, error, passes)


def _read_words(image, timeout, psm, scale, offset=(0, 0), line_override=None):
    try:
        data = pytesseract.image_to_data(image, lang="rus+eng", config=f"--oem 1 --psm {psm}",
                                        output_type=pytesseract.Output.DICT, timeout=max(0.01, timeout))
    except pytesseract.TesseractNotFoundError:
        return [], "unavailable"
    except pytesseract.TesseractError:
        return [], "engine_error"
    except RuntimeError as error:
        if "Tesseract process timeout" not in str(error):
            raise
        return [], "timeout"
    words = []
    for i, text in enumerate(data["text"]):
        confidence = float(data["conf"][i])
        if not text.strip() or confidence < 0:
            continue
        bbox = (round(data["left"][i] / scale) + offset[0], round(data["top"][i] / scale) + offset[1],
                round(data["width"][i] / scale), round(data["height"][i] / scale))
        line = line_override or (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        words.append(OcrWord(text.strip(), confidence, bbox, line))
    return words, None


def _bounds(words: list[OcrWord]) -> tuple[int, int, int, int]:
    x, y = min(w.bbox[0] for w in words), min(w.bbox[1] for w in words)
    right = max(w.bbox[0] + w.bbox[2] for w in words)
    bottom = max(w.bbox[1] + w.bbox[3] for w in words)
    return x, y, right - x, bottom - y


def extract_fields(words: list[OcrWord]) -> tuple[LabelField | None, LabelField | None]:
    years, strengths = [], []
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    for line in lines.values():
        text = " ".join(w.text for w in line)
        confidence = min(w.confidence for w in line)
        if confidence < 60:
            continue
        year = extract_year(text)
        if year and re.search(r"урожа|vintage|harvest", text, re.I) and not re.search(r"основан|since|founded|розлив|bottl", text, re.I):
            years.append(LabelField(year, text, _bounds(line), confidence, "vintage_context"))
        for match in re.finditer(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*(?:%|об\.?\b)|\balc\.?\s*(\d{1,2}(?:[.,]\d)?)(?![\d.,])", text, re.I):
            value = float((match.group(1) or match.group(2)).replace(",", "."))
            if 1 <= value <= 30:
                strengths.append(LabelField(value, text, _bounds(line), confidence, "alcohol_unit"))
    def unique(fields):
        return fields[0] if fields and len({f.value for f in fields}) == 1 else None
    return unique(years), unique(strengths)


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
    """Every distinct vintage year the label mentions, unlike extract_fields()'s
    single trusted-or-abstain value: a downstream ranking stage can weigh
    several readings against catalog evidence instead of losing them all to
    one ambiguous line."""
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
    """Every distinct alcohol-by-volume reading the label mentions, same
    all-candidates rationale as extract_year_candidates()."""
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


def text_score(text: str, wine: Wine) -> float:
    query_tokens = _tokens(text)
    catalog_tokens = _tokens(f"{wine.name} {wine.winery} {wine.slug}")
    if not query_tokens or not catalog_tokens:
        return 0.0

    matches = 0.0
    for catalog_token in catalog_tokens:
        best = max((_token_similarity(catalog_token, query_token) for query_token in query_tokens), default=0.0)
        if best >= 0.82:
            matches += best
    return min(1.0, matches / len(catalog_tokens))


def _tokens(value: str, *, stop_words: Collection[str] = STOP_WORDS) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold().translate(CYRILLIC_TO_LATIN)
    return {
        token
        for token in TOKEN_PATTERN.findall(normalized)
        if len(token) >= 3 and token not in stop_words
    }
