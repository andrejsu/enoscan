from __future__ import annotations

from collections import Counter
from math import log

from .catalog import Wine
from .ocr import _tokens
from .text_normalize import token_similarity as _token_similarity


class TextSearch:
    """Small catalog search; normalize once, fuzzy-match each query token once."""

    def __init__(self, wines: list[Wine]):
        self.wines = {w.slug: w for w in wines}
        self.documents = {
            w.slug: {t for t in _tokens(f"{w.name} {w.winery} {' '.join(w.grape_varieties)} {w.category or ''}") if not t.isdigit()}
            for w in self.wines.values()
        }
        counts = Counter(t for tokens in self.documents.values() for t in tokens)
        self.weights = {t: 1 + log((len(self.documents) + 1) / (n + 1)) for t, n in counts.items()}

    def scores(self, text: str) -> dict[str, float]:
        query = {t for t in _tokens(text) if not t.isdigit()}
        if not query:
            return {}
        matches = {}
        for token in self.weights:
            similarity = max((_token_similarity(token, q) for q in query if abs(len(q) - len(token)) <= 2), default=0)
            if similarity >= 0.82:
                matches[token] = similarity
        scores = {}
        for slug, tokens in self.documents.items():
            overlap = tokens & matches.keys()
            if not overlap:
                continue
            # Require two supported tokens, or one uncommon token. Generic words alone cannot recruit a wine.
            if len(overlap) < 2 and not any(self.weights[t] >= 2 for t in overlap):
                continue
            # Normalize against query evidence, not title length: identical observed words
            # must not prefer a short "Merlot" label over a longer "Cabernet Franc" title.
            scores[slug] = sum(self.weights[t] * matches[t] for t in overlap) / sum(self.weights[t] * matches[t] for t in matches)
        return scores

    def candidates(self, scores: dict[str, float], limit: int) -> list[Wine]:
        return [self.wines[slug] for slug in sorted(scores, key=lambda s: (-scores[s], s))[:limit]]
