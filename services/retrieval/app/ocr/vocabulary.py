from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection
from difflib import SequenceMatcher
from math import log
import re

from ..catalog import Wine
from ..label_fields import MAX_CANDIDATES, FieldCandidate
from .constants import (
    ALIAS_MIN_COUNT,
    ALIAS_MIN_SHARE,
    ALIAS_MIN_SIMILARITY,
    CATEGORY_SYNONYMS,
    CLOSED_VOCABULARY_FIELDS,
    MIN_TOKEN_LENGTH,
    STOP_WORDS,
    TOKEN_MATCH_SIMILARITY,
    UNCOMMON_TOKEN_WEIGHT,
)
from .tokens import phonetic_key, raw_tokens, token_similarity, tokenize


_LATIN_WORD = re.compile(r"[a-zà-öø-ÿ]+")
_CYRILLIC_WORD = re.compile(r"[а-яё]+")


def learn_aliases(wines: list[Wine]) -> dict[str, str]:
    latin_count: Counter[str] = Counter()
    together: dict[str, Counter[str]] = defaultdict(Counter)
    for wine in wines:
        text = " ".join([wine.name, wine.winery, wine.region or "", *wine.grape_varieties]).casefold()
        latin, cyrillic = _phonetic_keys(_LATIN_WORD, text), _phonetic_keys(_CYRILLIC_WORD, text)
        for word in latin:
            latin_count[word] += 1
            together[word].update(cyrillic - latin)
    aliases = {}
    for word, count in latin_count.items():
        best = max(((SequenceMatcher(None, word, other).ratio(), seen, other)
                    for other, seen in together[word].items()
                    if seen >= ALIAS_MIN_COUNT and seen / count >= ALIAS_MIN_SHARE), default=None)
        if best and best[0] >= ALIAS_MIN_SIMILARITY:
            aliases[word] = best[2]
    return aliases


def _phonetic_keys(pattern: re.Pattern, text: str) -> set[str]:
    return {phonetic_key(token) for word in pattern.findall(text)
            for token in raw_tokens(word) if len(token) >= MIN_TOKEN_LENGTH}


class FieldSearch:
    def __init__(self, values: set[str], *, stop_words: Collection[str] = STOP_WORDS,
                 allow_single_token: bool = False, exclude: dict[str, set[str]] | None = None,
                 aliases: dict[str, str] | None = None, synonyms: dict[str, str] | None = None,
                 known: Collection[str] = (), weak: Collection[str] = ()):
        self.stop_words = frozenset(stop_words)
        self.known = frozenset(known)
        # Words that never name a value on their own: «ПИНО» of «ПИНО НУАР» is a
        # grape, not the winery «Шато Пино» (every Шато Пино wine took its vote).
        self.weak = frozenset(weak)
        self.synonyms = synonyms or {}
        self.allow_single_token = allow_single_token
        self.aliases = aliases or {}
        exclude = exclude or {}
        self.documents = {}
        for value in values:
            terms = self._terms(value)
            self.documents[value] = (terms - exclude.get(value, set())) or terms
        counts = Counter(t for terms in self.documents.values() for t in terms)
        self.weights = {t: 1 + log((len(self.documents) + 1) / (n + 1)) for t, n in counts.items()}

    def _terms(self, text: str) -> set[str]:
        return {t for t in tokenize(text, stop_words=self.stop_words, aliases=self.aliases) if not t.isdigit()}

    def _similarity(self, token: str, query: str) -> float:
        """A word the catalog knows reads as that word: «МУСКАТЕЛЬ» is not also
        a fuzzy «Мускат». Unknown readings (OCR typos) match fuzzily."""
        if query in self.known:
            return 1.0 if token == query else 0.0
        return token_similarity(token, query)

    def explained(self, text: str, value: str) -> set[str]:
        return {q for q in self._terms(text)
                if any(self._similarity(t, q) >= TOKEN_MATCH_SIMILARITY for t in self.documents.get(value, ()))}

    def top(self, text: str, *, limit: int = MAX_CANDIDATES,
            ignore: Collection[str] = ()) -> tuple[FieldCandidate, ...]:
        synonyms = " ".join(self.synonyms[raw] for raw in raw_tokens(text) if raw in self.synonyms)
        query = self._terms(f"{text} {synonyms}") - set(ignore)
        if not query:
            return ()
        matches = {}
        for token in self.weights:
            similarity = max((self._similarity(token, q) for q in query), default=0)
            if similarity >= TOKEN_MATCH_SIMILARITY:
                matches[token] = similarity
        if not matches:
            return ()
        matched_pool = sum(self.weights[t] * matches[t] for t in matches)
        scores: dict[str, float] = {}
        for value, terms in self.documents.items():
            overlap = terms & matches.keys()
            if not overlap:
                continue
            if (len(overlap) < 2 and not self.allow_single_token
                    and not any(self.weights[t] >= UNCOMMON_TOKEN_WEIGHT for t in overlap)):
                continue
            if overlap <= self.weak:
                continue
            matched_weight = sum(self.weights[t] * matches[t] for t in overlap)
            value_weight = sum(self.weights[t] for t in terms)
            coverage = matched_weight / value_weight if value_weight else 0.0
            scores[value] = (matched_weight / matched_pool) * coverage
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return tuple(FieldCandidate(value, round(score, 4)) for value, score in ranked)


class FieldVocabulary:
    def __init__(self, wines: list[Wine]):
        self.aliases = learn_aliases(wines)
        known = {token for wine in wines for field in CLOSED_VOCABULARY_FIELDS
                 for value in wine.field_values(field) for token in tokenize(value, aliases=self.aliases)}
        grapes = {token for wine in wines for value in wine.field_values("grape_varieties")
                  for token in tokenize(value, aliases=self.aliases)}
        winery_tokens: dict[str, set[str]] = {}
        for wine in wines:
            winery_tokens.setdefault(wine.name.strip(), set()).update(tokenize(wine.winery, aliases=self.aliases))
        self._searches = {
            field: FieldSearch(
                {value for wine in wines for value in wine.field_values(field)},
                stop_words=() if field == "category" else STOP_WORDS,
                allow_single_token=field == "category",
                exclude=winery_tokens if field == "name" else None,
                aliases=self.aliases,
                synonyms=CATEGORY_SYNONYMS if field == "category" else None,
                known=known,
                weak=grapes if field == "winery" else (),
            )
            for field in CLOSED_VOCABULARY_FIELDS
        }

    def top(self, field: str, text: str, *, limit: int = MAX_CANDIDATES,
            ignore: Collection[str] = ()) -> tuple[FieldCandidate, ...]:
        return self._searches[field].top(text, limit=limit, ignore=ignore)

    def explained(self, field: str, text: str, value: str) -> set[str]:
        return self._searches[field].explained(text, value)
