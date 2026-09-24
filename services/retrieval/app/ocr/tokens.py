from __future__ import annotations

from collections.abc import Collection
from difflib import SequenceMatcher
import re
import unicodedata

from .constants import (
    FUZZY_MAX_LENGTH_GAP,
    FUZZY_MIN_LENGTH,
    MIN_TOKEN_LENGTH,
    PREFIX_MIN_LENGTH,
    PREFIX_SIMILARITY,
    STOP_WORDS,
)


_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_LATIN_ACCENTS = str.maketrans("àâäáéèêëíîïóôöúûüùçñ", "aaaaeeeeiiiooouuuucn")
_CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})
_PHONETIC_RULES = tuple((re.compile(pattern), replacement) for pattern, replacement in (
    (r"eau", "o"), (r"ch", "sh"), (r"oi", "ua"), (r"ou", "u"), (r"au", "o"), (r"ai", "e"), (r"gn", "n"),
    (r"ie", "i"), (r"ay$", "e"), (r"(?<=n)c$", ""), (r"(?<=[eo])[tdx]$", ""),
    (r"(?<=[aeiou])s(?=[aeiou])", "z"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"q", "k"), (r"w", "v"),
    (r"x", "ks"), (r"y", "i"), (r"(.)\1", r"\1"), (r"(?<=[^aeiou])e$", ""),
))


def phonetic_key(token: str) -> str:
    for pattern, replacement in _PHONETIC_RULES:
        token = pattern.sub(replacement, token)
    return token


def raw_tokens(value: str) -> list[str]:
    normalized = (unicodedata.normalize("NFKC", value).casefold()
                  .translate(_LATIN_ACCENTS).translate(_CYRILLIC_TO_LATIN))
    return _TOKEN.findall(normalized)


def tokenize(value: str, *, stop_words: Collection[str] = STOP_WORDS,
             aliases: dict[str, str] | None = None) -> set[str]:
    tokens = set()
    for raw in raw_tokens(value):
        if len(raw) < MIN_TOKEN_LENGTH or raw in stop_words:
            continue
        token = phonetic_key(raw)
        token = aliases.get(token, token) if aliases else token
        if len(token) >= MIN_TOKEN_LENGTH:
            tokens.add(token)
    return tokens


def token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if abs(len(left) - len(right)) > FUZZY_MAX_LENGTH_GAP:
        short, long = sorted((left, right), key=len)
        return PREFIX_SIMILARITY if len(short) >= PREFIX_MIN_LENGTH and long.startswith(short) else 0.0
    if min(len(left), len(right)) < FUZZY_MIN_LENGTH:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()
