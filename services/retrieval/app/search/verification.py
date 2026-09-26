"""The ranking's shortlist checked against what OCR read on the label
(verify_shortlist): each wine's name, winery, category, year and sugar level.
Why the ranking needs it — see search/ranking.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..catalog.models import Wine
from ..evidence import FieldCandidate, RetrievalFields
from ..label_text.sweetness import contradicts as sugar_contradicts
from ..label_text.tokens import TOKEN_MATCH_SIMILARITY, long_tokens, token_similarity
from ..label_text.vintage import extract_year


STYLE_WORDS = "брют brut экстра extra резерв reserve riserva сухое полусухое полусладкое сладкое классик classic"
STYLE_TOKENS = long_tokens(STYLE_WORDS)
WINERY_WORD_MAX_WINERIES = 2


@dataclass(frozen=True)
class LabelCheck:
    """One shortlisted wine checked against the label (verify_shortlist)."""
    slug: str
    read_words: tuple[str, ...]
    kind: str | None = None
    reason: str | None = None
    is_fully_read: bool = False


def only_value(candidates: tuple[FieldCandidate, ...]) -> str | None:
    """The field's value when OCR read exactly one, else None."""
    return candidates[0].value if len(candidates) == 1 else None


def catalog_words(name: str, tokens: set[str]) -> tuple[str, ...]:
    """The words of a wine name that carry these tokens, in catalog spelling."""
    words = []
    for word in name.replace("-", " ").split():
        word = word.strip(".,«»\"()")
        if long_tokens(word) & tokens and word not in words:
            words.append(word)
    return tuple(words)


def _name_tokens(wine: Wine) -> set[str]:
    """Words that tell this wine from its siblings: its name without its
    winery («Каберне Фран Сикоры» by Имение Сикоры) and without style words."""
    return long_tokens(wine.name) - long_tokens(wine.winery) - STYLE_TOKENS


def _seen_tokens(read: set[str], names: dict[str, set[str]]) -> dict[str, set[str]]:
    """Which name tokens of each shortlisted wine the label shows. A read word
    supports only the shortlisted words it matches best: «МУСКАТЕЛЬ» shows
    «Мускатель» of one wine, not also the weaker prefix match «Мускат» of another."""
    candidates = {t for tokens in names.values() for t in tokens}
    supported = set()
    for word in read:
        similarities = {t: token_similarity(t, word) for t in candidates}
        best = max(similarities.values(), default=0.0)
        if best >= TOKEN_MATCH_SIMILARITY:
            supported |= {t for t, similarity in similarities.items() if similarity == best}
    return {slug: tokens & supported for slug, tokens in names.items()}


@lru_cache(maxsize=4)
def _generic_winery_tokens(wineries_and_regions: frozenset[tuple[str, str]]) -> frozenset[str]:
    """Winery words shared by more than WINERY_WORD_MAX_WINERIES wineries, and
    region words («КУБАНЬ» is not «Кубань-Вино»)."""
    wineries: dict[str, set[str]] = {}
    regions: set[str] = set()
    for winery, region in wineries_and_regions:
        for token in long_tokens(winery):
            wineries.setdefault(token, set()).add(winery)
        regions |= long_tokens(region)
    return frozenset({token for token, names in wineries.items() if len(names) > WINERY_WORD_MAX_WINERIES} | regions)


def generic_winery_tokens(wines: list[Wine]) -> frozenset[str]:
    return _generic_winery_tokens(frozenset((wine.winery.strip(), (wine.region or "").strip()) for wine in wines))


def _shows(label: set[str], tokens: set[str]) -> bool:
    return any(token_similarity(token, word) >= TOKEN_MATCH_SIMILARITY for token in tokens for word in label)


def verify_shortlist(shortlist: list[Wine], ocr_fields: RetrievalFields, ocr_text: str,
                     generic_winery: frozenset[str] = frozenset()) -> tuple[LabelCheck, ...]:
    """Check each shortlisted wine against what OCR read.

    A name contradicts a wine only when the label shows a long word of a
    rival's name that this wine's name lacks, while nothing on the label
    speaks for this wine over that rival. Short or shared words (a line name,
    «Пет-Нат») never do: they fit every sibling equally. A category, year or
    sugar level contradicts only when OCR read exactly one and the wine has
    another («РОЗОВОЕ ПОЛУСУХОЕ» against its «сухое» and «полусладкое» twins).
    A winery contradicts when the label shows a distinctive word of the winery
    OCR read, and nothing of this wine's own winery or name: «ТАБИЯ … Пино
    Нуар» is not Новый Свет's Pinot Noir. ``generic_winery`` are winery words
    that name no winery in particular (generic_winery_tokens)."""
    names = {wine.slug: _name_tokens(wine) for wine in shortlist}
    label = long_tokens(ocr_text)
    seen = _seen_tokens(label, names)
    read_winery = ocr_fields.winery[0].value.strip() if ocr_fields.winery else None
    is_winery_shown = bool(read_winery) and _shows(label, long_tokens(read_winery) - generic_winery)
    category, year = only_value(ocr_fields.category), only_value(ocr_fields.year)
    sweetness = only_value(ocr_fields.sweetness)
    checks = []
    for wine in shortlist:
        read_words = catalog_words(wine.name, seen[wine.slug])
        fully = bool(names[wine.slug]) and seen[wine.slug] == names[wine.slug]
        for rival in shortlist:
            if rival.slug == wine.slug:
                continue
            speaks_for_rival = seen[rival.slug] - names[wine.slug]
            speaks_for_wine = seen[wine.slug] - names[rival.slug]
            if speaks_for_rival and not speaks_for_wine:
                words = ", ".join(f"«{word}»" for word in catalog_words(rival.name, speaks_for_rival))
                checks.append(LabelCheck(wine.slug, read_words, "name",
                                         f"на этикетке {words} из «{rival.name.strip()}», в этом названии их нет",
                                         fully))
                break
        else:
            wine_year = extract_year(wine.name)
            if (is_winery_shown and wine.winery.strip() != read_winery and not seen[wine.slug]
                    and not _shows(label, long_tokens(wine.winery) - generic_winery)):
                checks.append(LabelCheck(wine.slug, read_words, "winery",
                                         f"на этикетке «{read_winery}», в каталоге «{wine.winery.strip()}»", fully))
            elif category and wine.category and wine.category.strip() != category:
                checks.append(LabelCheck(wine.slug, read_words, "category",
                                         f"на этикетке {category}, в каталоге {wine.category.strip()}", fully))
            elif year and wine_year is not None and str(wine_year) != year:
                checks.append(LabelCheck(wine.slug, read_words, "year",
                                         f"на этикетке {year}, в каталоге {wine_year}", fully))
            elif sweetness and wine.sweetness and sugar_contradicts(sweetness, wine.sweetness):
                checks.append(LabelCheck(wine.slug, read_words, "sweetness",
                                         f"на этикетке {sweetness}, в каталоге {wine.sweetness}", fully))
            else:
                checks.append(LabelCheck(wine.slug, read_words, is_fully_read=fully))
    return tuple(checks)
