"""Catalog wines to suggest when a scan does not match (app/ranking.py).

A photo of a wine outside the catalog often still shows a winery, a line or
a grape the catalog knows: «Массандра Мускатель белый 2023» when the catalog
has only another vintage, a new cuvée of «Инкерманский ЗМВ». Those wines
are not the answer — ranking already said so — but they are the honest next
step: the same producer, the same line, the same grape.

This never changes the ranking decision or a score. It reads the ranking's
evidence and what OCR read on the label, and keeps only wines that share
something distinctive with the label: a word of the wine's own name, or its
winery together with a grape, colour or sugar level the label states. A
winery alone is not enough — «Фанагория» on a new label says only that the
wine is theirs, and suggesting any of their hundred wines is a guess. Nor is
«Красное сухое», shared by hundreds of wines.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .catalog import Wine
from .label_fields import RetrievalFields
from .ocr.constants import FUZZY_MIN_LENGTH, TOKEN_MATCH_SIMILARITY
from .ocr.fields import extract_year
from .ocr.tokens import token_similarity, tokenize
from .ranking import STYLE_WORDS, RankingResult


RECOMMENDATION_LIMIT = 3

# How far down the ranking to look. Wines below have no evidence the label
# and the photo share anything with them.
RECOMMENDATION_POOL = 30

# Label fields a recommended wine may share with the photo, in the order the
# reason names them. `name` means a distinctive word of the wine's own name.
SHARED_FIELDS = ("name", "winery", "grape_varieties", "category", "sweetness", "region", "year")

# The winery ties a wine to the label only together with one of these.
WINERY_COMPANIONS = ("grape_varieties", "category", "sweetness")

# A name word used by more wineries than this is a common word («Винодельня»,
# «Мускат», «Резерв»), not a line: it ties the label to nothing in particular.
NAME_WORD_MAX_WINERIES = 2


@dataclass(frozen=True)
class Recommendation:
    slug: str
    score: float  # the ranking's evidence for this wine, as in the scan's candidates
    shared_fields: tuple[str, ...]  # SHARED_FIELDS this wine has in common with the label
    reason: str  # human-readable, for the result page
    difference: str | None = None  # what the label contradicts, when ranking rejected this wine


def _long_tokens(text: str) -> set[str]:
    return {token for token in tokenize(text) if len(token) >= FUZZY_MIN_LENGTH and not token.isdigit()}


_STYLE_TOKENS = _long_tokens(STYLE_WORDS)


def _own_name_tokens(wine: Wine) -> set[str]:
    """Words that name this wine and not its winery, style or grape:
    «Purity» of «Purity in Merlot», not «Merlot» — a grape is its own field —
    and not «Inkerman» of «Инкерманский ЗМВ», the winery's brand."""
    grapes = set().union(*(_long_tokens(grape) for grape in wine.grape_varieties))
    winery = _long_tokens(wine.winery)
    return {token for token in _long_tokens(wine.name) - _STYLE_TOKENS - grapes
            if all(token_similarity(token, word) < TOKEN_MATCH_SIMILARITY for word in winery)}


def common_name_tokens(wines: Iterable[Wine]) -> frozenset[str]:
    """Words more than NAME_WORD_MAX_WINERIES wineries use in a wine or winery
    name: «Винодельня» sits in one wine's name and in dozens of winery names."""
    wineries: dict[str, set[str]] = defaultdict(set)
    for wine in wines:
        for token in _long_tokens(wine.name) | _long_tokens(wine.winery):
            wineries[token].add(wine.winery.strip())
    return frozenset(token for token, names in wineries.items() if len(names) > NAME_WORD_MAX_WINERIES)


def _shown_words(wine: Wine, label_tokens: set[str], common: frozenset[str]) -> tuple[str, ...]:
    """Distinctive words of the wine's name, as the catalog spells them, that the label shows."""
    shown = {token for token in _own_name_tokens(wine) - common
             if any(token_similarity(token, read) >= TOKEN_MATCH_SIMILARITY for read in label_tokens)}
    words = []
    for word in wine.name.replace("-", " ").split():
        word = word.strip(".,«»\"()")
        if _long_tokens(word) & shown and word not in words:
            words.append(word)
    return tuple(words)


def _top(ocr_fields: RetrievalFields, field: str) -> str | None:
    candidates = getattr(ocr_fields, field)
    return candidates[0].value if candidates else None


def _shared(wine: Wine, ocr_fields: RetrievalFields, label_tokens: set[str],
            common: frozenset[str]) -> dict[str, str]:
    """field -> the value the label and this wine have in common."""
    shared = {}
    if words := _shown_words(wine, label_tokens, common):
        shared["name"] = ", ".join(f"«{word}»" for word in words)
    winery = _top(ocr_fields, "winery")
    # «Винодельня 78» read off «Семейная винодельня Литавщуков»: a winery whose
    # name is only common words and digits is no evidence of the winery.
    if winery and winery == wine.winery.strip() and set(tokenize(winery)) - common - _digits(winery):
        shared["winery"] = winery
    for field in ("grape_varieties", "category", "region"):
        value = _top(ocr_fields, field)
        if value and value in wine.field_values(field):
            shared[field] = value
    if (sweetness := _top(ocr_fields, "sweetness")) and wine.sweetness == sweetness:
        shared["sweetness"] = sweetness
    if (year := _top(ocr_fields, "year")) and str(extract_year(wine.name)) == year:
        shared["year"] = year
    return shared


def _digits(text: str) -> set[str]:
    return {token for token in tokenize(text) if token.isdigit()}


def _is_related(shared: dict[str, str]) -> bool:
    if "name" in shared:
        return True
    return "winery" in shared and any(field in shared for field in WINERY_COMPANIONS)


_REASON_LABELS = {
    "name": "в названии {}", "winery": "та же винодельня «{}»", "grape_varieties": "сорт {}",
    "category": "{}", "sweetness": "{}", "region": "регион {}", "year": "урожай {}",
}


def _reason(shared: dict[str, str]) -> str:
    parts = [_REASON_LABELS[field].format(shared[field]) for field in SHARED_FIELDS if field in shared]
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


def recommend(result: RankingResult, ocr_fields: RetrievalFields, wines_by_slug: dict[str, Wine],
              *, ocr_text: str = "", common_tokens: frozenset[str] | None = None,
              limit: int = RECOMMENDATION_LIMIT) -> tuple[Recommendation, ...]:
    """Related catalog wines for a scan that did not match, best evidence first.

    A matched scan gets none: the answer is already there. Wines the label
    contradicts (another vintage, another colour) stay — for a wine outside
    the catalog they are exactly the neighbours worth showing — and say what
    differs. ``common_tokens`` is common_name_tokens of the catalog; pass it
    precomputed, it is derived from ``wines_by_slug`` otherwise."""
    if common_tokens is None:
        common_tokens = common_name_tokens(wines_by_slug.values())
    if result.status == "matched":
        return ()
    label_tokens = _long_tokens(ocr_text)
    by_evidence = sorted(((slug, score) for slug, score in result.evidence.items() if score > 0),
                         key=lambda item: (-item[1], item[0]))
    recommendations = []
    for slug, score in by_evidence[:RECOMMENDATION_POOL]:
        wine = wines_by_slug.get(slug)
        if wine is None:
            continue
        shared = _shared(wine, ocr_fields, label_tokens, common_tokens)
        if not _is_related(shared):
            continue
        recommendations.append(Recommendation(
            slug, score, tuple(field for field in SHARED_FIELDS if field in shared), _reason(shared),
            result.rejected.get(slug),
        ))
        if len(recommendations) == limit:
            break
    return tuple(recommendations)
