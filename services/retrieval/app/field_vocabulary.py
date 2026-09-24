from __future__ import annotations

from collections.abc import Collection
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from math import log
import re

from .catalog import Wine
from .label_fields import MAX_CANDIDATES, FieldCandidate
from .ocr import STOP_WORDS, _raw_tokens, _tokens, phonetic_key
from .text_normalize import token_similarity as _token_similarity


CLOSED_VOCABULARY_FIELDS = ("name", "winery", "grape_varieties", "category", "color", "region")


def _field_values(wine: Wine, field: str) -> list[str]:
    if field == "grape_varieties":
        return [item.strip() for item in wine.grape_varieties if item.strip()]
    raw = getattr(wine, field)
    return [raw.strip()] if raw else []


_LATIN_WORD = re.compile(r"[a-zà-öø-ÿ]+")
_CYRILLIC_WORD = re.compile(r"[а-яё]+")


def learn_aliases(wines: list[Wine], *, min_count: int = 2, min_share: float = 0.3,
                  min_similarity: float = 0.75) -> dict[str, str]:
    """Latin label spellings the catalog itself pairs with a Cyrillic one,
    for what phonetic_key() alone can't fold ("Kodzor" / "Кодзора"): the
    Latin word appears alongside that similar-sounding Cyrillic word in at
    least ``min_share`` of the wines it occurs in."""
    def keys(pattern: re.Pattern, text: str) -> set[str]:
        return {phonetic_key(t) for word in pattern.findall(text) for t in _raw_tokens(word) if len(t) >= 3}

    latin_count: Counter[str] = Counter()
    together: dict[str, Counter[str]] = defaultdict(Counter)
    for wine in wines:
        text = " ".join([wine.name, wine.winery, wine.region or "", *wine.grape_varieties]).casefold()
        latin, cyrillic = keys(_LATIN_WORD, text), keys(_CYRILLIC_WORD, text)
        for word in latin:
            latin_count[word] += 1
            together[word].update(cyrillic - latin)
    aliases = {}
    for word, count in latin_count.items():
        best = max(((SequenceMatcher(None, word, other).ratio(), seen, other)
                    for other, seen in together[word].items()
                    if seen >= min_count and seen / count >= min_share), default=None)
        if best and best[0] >= min_similarity:
            aliases[word] = best[2]
    return aliases


PREFIX_MIN_LENGTH = 6
PREFIX_SIMILARITY = 0.9


def _similarity(token: str, query: str) -> float:
    if abs(len(query) - len(token)) <= 2:
        return _token_similarity(token, query)
    short, long = sorted((token, query), key=len)
    return PREFIX_SIMILARITY if len(short) >= PREFIX_MIN_LENGTH and long.startswith(short) else 0.0


class FieldSearch:
    def __init__(self, values: set[str], *, stop_words: Collection[str] = STOP_WORDS,
                 allow_single_token: bool = False, exclude: dict[str, set[str]] | None = None,
                 aliases: dict[str, str] | None = None):
        self.stop_words = frozenset(stop_words)
        self.allow_single_token = allow_single_token
        self.aliases = aliases or {}
        exclude = exclude or {}
        self.documents = {}
        for value in values:
            tokens = {t for t in _tokens(value, stop_words=stop_words, aliases=self.aliases) if not t.isdigit()}
            self.documents[value] = (tokens - exclude.get(value, set())) or tokens
        counts = Counter(t for tokens in self.documents.values() for t in tokens)
        self.weights = {t: 1 + log((len(self.documents) + 1) / (n + 1)) for t, n in counts.items()}

    def _query(self, text: str) -> set[str]:
        return {t for t in _tokens(text, stop_words=self.stop_words, aliases=self.aliases) if not t.isdigit()}

    def explained(self, text: str, value: str) -> set[str]:
        """Query tokens that match ``value``'s own tokens."""
        return {q for q in self._query(text)
                if any(_similarity(t, q) >= 0.82 for t in self.documents.get(value, ()))}

    def top(self, text: str, *, limit: int = MAX_CANDIDATES,
            ignore: Collection[str] = ()) -> tuple[FieldCandidate, ...]:
        query = self._query(text) - set(ignore)
        if not query:
            return ()
        matches = {}
        for token in self.weights:
            similarity = max((_similarity(token, q) for q in query), default=0)
            if similarity >= 0.82:
                matches[token] = similarity
        if not matches:
            return ()
        matched_pool = sum(self.weights[t] * matches[t] for t in matches)
        scores: dict[str, float] = {}
        for value, tokens in self.documents.items():
            overlap = tokens & matches.keys()
            if not overlap:
                continue
            if (len(overlap) < 2 and not self.allow_single_token
                    and not any(self.weights[t] >= 2 for t in overlap)):
                continue
            matched_weight = sum(self.weights[t] * matches[t] for t in overlap)
            value_weight = sum(self.weights[t] for t in tokens)
            coverage = matched_weight / value_weight if value_weight else 0.0
            scores[value] = (matched_weight / matched_pool) * coverage
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return tuple(FieldCandidate(value, round(score, 4)) for value, score in ranked)


class FieldVocabulary:
    """One FieldSearch per closed-vocabulary field, built once from the catalog."""

    def __init__(self, wines: list[Wine]):
        # "Aligote. Шато Пино": the winery's words inside a name are winery
        # evidence, not name evidence. Counting them twice let a label that
        # only showed "CHATEAU PINOT" match the one wine that repeats its
        # winery in its name, and pass ranking's name-or-visual gate.
        self.aliases = learn_aliases(wines)
        winery_tokens: dict[str, set[str]] = {}
        for wine in wines:
            winery_tokens.setdefault(wine.name.strip(), set()).update(_tokens(wine.winery, aliases=self.aliases))
        self._searches = {
            field: FieldSearch(
                {value for wine in wines for value in _field_values(wine, field)},
                stop_words=() if field == "category" else STOP_WORDS,
                allow_single_token=field == "category",
                exclude=winery_tokens if field == "name" else None,
                aliases=self.aliases,
            )
            for field in CLOSED_VOCABULARY_FIELDS
        }

    def top(self, field: str, text: str, *, limit: int = MAX_CANDIDATES,
            ignore: Collection[str] = ()) -> tuple[FieldCandidate, ...]:
        return self._searches[field].top(text, limit=limit, ignore=ignore)

    def explained(self, field: str, text: str, value: str) -> set[str]:
        return self._searches[field].explained(text, value)
