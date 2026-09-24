"""Per-field fuzzy vocabulary search for closed-vocabulary catalog fields.

Generalizes text_search.py's token/IDF-weighting approach (reused, not
reinvented) but keyed by distinct field *value* instead of by whole wine —
text_search.py resolves straight to a wine; this resolves to plausible
values for one field, which is what app/ocr_retriever.py needs to fill
app/label_fields.py's RetrievalFields.
"""

from __future__ import annotations

from collections.abc import Collection
from collections import Counter
from math import log

from .catalog import Wine
from .label_fields import MAX_CANDIDATES, FieldCandidate
from .ocr import STOP_WORDS, _tokens
from .text_normalize import token_similarity as _token_similarity


CLOSED_VOCABULARY_FIELDS = ("name", "winery", "grape_varieties", "category", "color", "region")


def _field_values(wine: Wine, field: str) -> list[str]:
    if field == "grape_varieties":
        return [item.strip() for item in wine.grape_varieties if item.strip()]
    raw = getattr(wine, field)
    return [raw.strip()] if raw else []


class FieldSearch:
    """Fuzzy search over one field's distinct catalog values; normalize once,
    fuzzy-match each query token once — same shape as text_search.TextSearch."""

    def __init__(self, values: set[str], *, stop_words: Collection[str] = STOP_WORDS,
                 allow_single_token: bool = False):
        self.stop_words = frozenset(stop_words)
        self.allow_single_token = allow_single_token
        self.documents = {
            value: {t for t in _tokens(value, stop_words=stop_words) if not t.isdigit()}
            for value in values
        }
        counts = Counter(t for tokens in self.documents.values() for t in tokens)
        self.weights = {t: 1 + log((len(self.documents) + 1) / (n + 1)) for t, n in counts.items()}

    def top(self, text: str, *, limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
        query = {t for t in _tokens(text, stop_words=self.stop_words) if not t.isdigit()}
        if not query:
            return ()
        matches = {}
        for token in self.weights:
            similarity = max((_token_similarity(token, q) for q in query if abs(len(q) - len(token)) <= 2), default=0)
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
            # Same guard as TextSearch: two supported tokens, or one uncommon token.
            # Small enum-like fields can explicitly accept one supported token.
            if (len(overlap) < 2 and not self.allow_single_token
                    and not any(self.weights[t] >= 2 for t in overlap)):
                continue
            matched_weight = sum(self.weights[t] * matches[t] for t in overlap)
            value_weight = sum(self.weights[t] for t in tokens)
            # Share of query evidence this candidate accounts for, discounted
            # by how much of the candidate's OWN identity that evidence
            # actually covers. Without the coverage factor, one coincidental
            # rare-token match against a multi-word name reads as full
            # confidence just because nothing else in the whole vocabulary
            # happened to match anything either — real bug, not hypothetical:
            # garbled OCR on an unrelated photo matched a single token of
            # "MILLSTREAM Cellar Резерв Бленд №4" and scored 1.0.
            coverage = matched_weight / value_weight if value_weight else 0.0
            scores[value] = (matched_weight / matched_pool) * coverage
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return tuple(FieldCandidate(value, round(score, 4)) for value, score in ranked)


class FieldVocabulary:
    """One FieldSearch per closed-vocabulary field, built once from the catalog."""

    def __init__(self, wines: list[Wine]):
        self._searches = {
            field: FieldSearch(
                {value for wine in wines for value in _field_values(wine, field)},
                stop_words=() if field == "category" else STOP_WORDS,
                allow_single_token=field == "category",
            )
            for field in CLOSED_VOCABULARY_FIELDS
        }

    def top(self, field: str, text: str, *, limit: int = MAX_CANDIDATES) -> tuple[FieldCandidate, ...]:
        return self._searches[field].top(text, limit=limit)
