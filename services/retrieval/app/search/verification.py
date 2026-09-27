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
from ..label_text.tokens import TOKEN_MATCH_SIMILARITY, long_tokens, token_similarity, tokenize
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


def _name_tokens(wine: Wine, common_short: frozenset[str] = frozenset()) -> set[str]:
    """Words that tell this wine from its siblings: its name without its
    winery («Каберне Фран Сикоры» by Имение Сикоры) and without style words.
    A name of short words only keeps those few wineries use («Олег» of Табия),
    not ones every label of a grape carries («Пино Нуар»: common_short_name_tokens).
    Short words compare only exactly (token_similarity)."""
    tokens = long_tokens(wine.name) - long_tokens(wine.winery) - STYLE_TOKENS
    return tokens or (_words(wine.name) - _words(wine.winery) - STYLE_TOKENS - common_short)


def _words(text: str) -> set[str]:
    return {token for token in tokenize(text) if not token.isdigit()}


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


@lru_cache(maxsize=4)
def _common_short_name_tokens(names_and_wineries: frozenset[tuple[str, str]]) -> frozenset[str]:
    wineries: dict[str, set[str]] = {}
    for name, winery in names_and_wineries:
        for token in _words(name) - long_tokens(name):
            wineries.setdefault(token, set()).add(winery)
    return frozenset(token for token, names in wineries.items() if len(names) > WINERY_WORD_MAX_WINERIES)


def common_short_name_tokens(wines: list[Wine]) -> frozenset[str]:
    """Short name words more than WINERY_WORD_MAX_WINERIES wineries use: «Пино», «Нуар», «Розе»."""
    return _common_short_name_tokens(frozenset((wine.name.strip(), wine.winery.strip()) for wine in wines))


def generic_winery_tokens(wines: list[Wine]) -> frozenset[str]:
    return _generic_winery_tokens(frozenset((wine.winery.strip(), (wine.region or "").strip()) for wine in wines))


# «ОРАНЖ» on a label is a style the catalog files both ways: 20 of its 32
# orange wines are «Белое», but every one of those says «Оранж» in its name.
ORANGE = "Оранжевое"
ORANGE_NAME_TOKENS = long_tokens("оранж orange")


def category_contradicts(label: str, wine: Wine) -> bool:
    category = (wine.category or "").strip()
    if label == ORANGE:
        return category != ORANGE and not _shows(long_tokens(wine.name), ORANGE_NAME_TOKENS)
    return category != label


def _shows(label: set[str], tokens: set[str]) -> bool:
    return any(token_similarity(token, word) >= TOKEN_MATCH_SIMILARITY for token in tokens for word in label)


def label_grapes(ocr_fields: RetrievalFields, label: set[str]) -> tuple[str, ...]:
    """Grapes the label spells out in full: every long word of the grape is on
    it, exactly. «ЦИТРОН» alone is not «Цитронный Магарача», and a neighbour's cut-off
    «МУСКА» is not «Мускат»: this only rejects wines, so a misread must not count."""
    grapes = []
    for candidate in ocr_fields.grape_varieties:
        tokens = _words(candidate.value)
        if tokens and tokens <= label and candidate.value not in grapes:
            grapes.append(candidate.value)
    return tuple(grapes)


def _grape_fits(grape: str, wine: Wine) -> bool:
    own = _words(" ".join((wine.name, *wine.grape_varieties)))
    return all(any(token_similarity(token, word) >= TOKEN_MATCH_SIMILARITY for word in own)
               for token in _words(grape))


def verify_shortlist(shortlist: list[Wine], ocr_fields: RetrievalFields, ocr_text: str,
                     generic_winery: frozenset[str] = frozenset(),
                     common_short: frozenset[str] = frozenset()) -> tuple[LabelCheck, ...]:
    """Check each shortlisted wine against what OCR read.

    A name contradicts a wine only when the label shows a long word of a
    rival's name that this wine's name lacks, while nothing on the label
    speaks for this wine over that rival. Short or shared words (a line name,
    «Пет-Нат») never do: they fit every sibling equally. A category, year or
    sugar level contradicts only when OCR read exactly one and the wine has
    another («РОЗОВОЕ ПОЛУСУХОЕ» against its «сухое» and «полусладкое» twins).
    A grape contradicts when the label spells out grapes (label_grapes) and
    none of them is among the wine's grapes or in its name: «PINOT GRIS» is
    not a Muscat brut.
    A winery contradicts when the label shows a distinctive word of the winery
    OCR read, and nothing of this wine's own winery or name: «ТАБИЯ … Пино
    Нуар» is not Новый Свет's Pinot Noir. ``generic_winery`` are winery words
    that name no winery in particular (generic_winery_tokens)."""
    names = {wine.slug: _name_tokens(wine, common_short) for wine in shortlist}
    label = _words(ocr_text)
    seen = _seen_tokens(label, names)
    # The first winery OCR proposes whose own distinctive word the label shows:
    # «СЕМЕЙНАЯ ВИНОДЕЛЬНЯ ЛИТАВЩУКОВ» ranks ЛОРИО («семейная винодельня») first,
    # but only «Литавщук» is written there.
    read_winery = next((candidate.value.strip() for candidate in ocr_fields.winery
                        if _shows(label, long_tokens(candidate.value) - generic_winery)), None)
    is_winery_shown = read_winery is not None
    category, year = only_value(ocr_fields.category), only_value(ocr_fields.year)
    sweetness = only_value(ocr_fields.sweetness)
    grapes = label_grapes(ocr_fields, label)
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
            elif category and wine.category and category_contradicts(category, wine):
                checks.append(LabelCheck(wine.slug, read_words, "category",
                                         f"на этикетке {category}, в каталоге {wine.category.strip()}", fully))
            elif year and wine_year is not None and str(wine_year) != year:
                checks.append(LabelCheck(wine.slug, read_words, "year",
                                         f"на этикетке {year}, в каталоге {wine_year}", fully))
            elif sweetness and wine.sweetness and sugar_contradicts(sweetness, wine.sweetness):
                checks.append(LabelCheck(wine.slug, read_words, "sweetness",
                                         f"на этикетке {sweetness}, в каталоге {wine.sweetness}", fully))
            elif grapes and wine.grape_varieties and not any(_grape_fits(grape, wine) for grape in grapes):
                checks.append(LabelCheck(wine.slug, read_words, "grape",
                                         f"на этикетке {', '.join(grapes)}, в каталоге "
                                         f"{', '.join(wine.grape_varieties)}", fully))
            else:
                checks.append(LabelCheck(wine.slug, read_words, is_fully_read=fully))
    return tuple(checks)
