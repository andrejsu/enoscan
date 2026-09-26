"""Combine OCR's per-field evidence (app/ocr/retriever.py) with the visual
retriever's slug evidence (app/retriever.py) into one resolved wine slug.
Neither producer resolves a wine itself — this is the one place that does,
and the one place that decides between an honest not_found and a match.

Raw producer scores are not comparable across fields: OCR's name scores
shrink as the label gets noisier (a clear winner can sit at 0.28), and a
wine used to collect credit from whichever of 50 candidates happened to
match it. So each field is first turned into a distribution over its own
candidates — the field's top-1 carries most of the mass, near-ties share
it, low-ranked candidates get almost none. A field that can't tell
candidates apart then can't reorder them.

Fields only ever add support: a wine's score is the weighted sum of its
per-field probabilities over the fixed total of FIELD_WEIGHTS, so a field
that agrees raises the score, and a field that has no opinion about this
wine adds nothing instead of dragging the others down. The score reads as
"share of the full support a wine could get", and a clear match that both
the retriever and OCR back sits around 0.4-0.8.

Because fields only add, a visual leader the label plainly contradicts
still wins on the visual weight alone. So before deciding, the top of the
ranking is checked against what OCR read (verify_shortlist): a wine is
rejected when the label shows a distinctive word of a rival's name that its
own name lacks, or a category/year that differs from its own. Rejected wines
drop below the rest; scores stay as they are.

The decision is the gap between the first and second wine (TZ: «отрыв
между 1-м и 2-м результатом»), not an absolute score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from math import exp

from .catalog import Wine
from .label_fields import FieldCandidate, RetrievalFields
from .ocr.constants import FUZZY_MIN_LENGTH, TOKEN_MATCH_SIMILARITY
from .ocr.fields import extract_year
from .ocr.tokens import token_similarity, tokenize
from .sweetness import contradicts as sugar_contradicts


FIELD_WEIGHTS = {
    "slug": 0.70, "name": 0.20, "winery": 0.20, "grape_varieties": 0.12,
    "year": 0.08, "region": 0.04, "category": 0.03,
}
TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())

VISUAL_TEMPERATURE = 0.05
OCR_TEMPERATURE = 0.06

MIN_MARGIN = 0.03

VISUAL_IDENTIFY_MIN = 0.25
CONFIRMING_FIELDS = ("year",)

VERIFY_SHORTLIST = 3
VERIFY_LIMIT = 8

STYLE_WORDS = "брют brut экстра extra резерв reserve riserva сухое полусухое полусладкое сладкое классик classic"
HARD_CONTRADICTIONS = ("winery", "category", "year", "sweetness")
WINERY_WORD_MAX_WINERIES = 2


@dataclass(frozen=True)
class RankingResult:
    status: str
    slug: str | None
    score: float
    margin: float
    evidence: dict[str, float]
    rejected: dict[str, str] = field(default_factory=dict)
    checks: tuple["LabelCheck", ...] = ()

    def ranked(self, limit: int) -> list[tuple[str, float]]:
        return _ranked(self.evidence, limit, self.rejected)


def _ranked(evidence: dict[str, float], limit: int,
            rejected: dict[str, str] | None = None) -> list[tuple[str, float]]:
    rejected = rejected or {}
    return sorted(evidence.items(), key=lambda item: (item[0] in rejected, -item[1], item[0]))[:limit]


@dataclass(frozen=True)
class FieldContribution:
    field: str
    weight: float
    score: float


def _actual_values(wine: Wine, field: str) -> set[str]:
    if field == "slug":
        return {wine.slug}
    if field == "year":
        year = extract_year(wine.name)
        return {str(year)} if year is not None else set()
    return set(wine.field_values(field))


def field_distribution(candidates: tuple[FieldCandidate, ...], temperature: float) -> dict[str, float]:
    """Softmax over one field's candidates, relative to its own top-1."""
    top = max(candidate.score for candidate in candidates)
    weights: dict[str, float] = {}
    for candidate in candidates:
        weight = exp((candidate.score - top) / temperature)
        weights[candidate.value] = max(weights.get(candidate.value, 0.0), weight)
    total = sum(weights.values())
    return {value: weight / total for value, weight in weights.items()}


def _distributions(ocr_fields: RetrievalFields, visual_fields: RetrievalFields) -> dict[str, dict[str, float]]:
    distributions = {}
    for field in FIELD_WEIGHTS:
        candidates = visual_fields.slug if field == "slug" else getattr(ocr_fields, field)
        if candidates:
            temperature = VISUAL_TEMPERATURE if field == "slug" else OCR_TEMPERATURE
            distributions[field] = field_distribution(candidates, temperature)
    return distributions


def _contributions(wine: Wine, distributions: dict[str, dict[str, float]]) -> tuple[FieldContribution, ...]:
    terms = tuple(
        FieldContribution(field, FIELD_WEIGHTS[field],
                          max((distribution[value] for value in _actual_values(wine, field) if value in distribution),
                              default=0.0))
        for field, distribution in distributions.items()
    )
    if any(term.field == "name" and term.score > 0 for term in terms):
        return terms
    return tuple(FieldContribution(term.field, term.weight, 0.0) if term.field in CONFIRMING_FIELDS else term
                 for term in terms)


def field_breakdown(wine: Wine, ocr_fields: RetrievalFields,
                    visual_fields: RetrievalFields) -> tuple[FieldContribution, ...]:
    """Per-field terms of the wine's score, for fields that produced any
    candidates; weight × score / TOTAL_WEIGHT is each field's share."""
    return _contributions(wine, _distributions(ocr_fields, visual_fields))


def _score(contributions: tuple[FieldContribution, ...]) -> float:
    return sum(item.weight * item.score for item in contributions) / TOTAL_WEIGHT


def _long_tokens(text: str) -> set[str]:
    return {token for token in tokenize(text) if len(token) >= FUZZY_MIN_LENGTH and not token.isdigit()}


_STYLE_TOKENS = _long_tokens(STYLE_WORDS)


def _name_tokens(wine: Wine) -> set[str]:
    """Words that tell this wine from its siblings: its name without its
    winery («Каберне Фран Сикоры» by Имение Сикоры) and without style words."""
    return _long_tokens(wine.name) - _long_tokens(wine.winery) - _STYLE_TOKENS


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


def only_value(candidates: tuple[FieldCandidate, ...]) -> str | None:
    """The field's value when OCR read exactly one, else None."""
    return candidates[0].value if len(candidates) == 1 else None


@dataclass(frozen=True)
class LabelCheck:
    """One shortlisted wine checked against the label (verify_shortlist)."""
    slug: str
    read_words: tuple[str, ...]
    kind: str | None = None
    reason: str | None = None
    is_fully_read: bool = False


def _catalog_words(wine: Wine, tokens: set[str]) -> tuple[str, ...]:
    """The words of the wine's name that carry these tokens, in catalog spelling."""
    words = []
    for word in wine.name.replace("-", " ").split():
        if _long_tokens(word) & tokens and word.strip(".,«»\"()") not in words:
            words.append(word.strip(".,«»\"()"))
    return tuple(words)


@lru_cache(maxsize=4)
def _generic_winery_tokens(wineries_and_regions: frozenset[tuple[str, str]]) -> frozenset[str]:
    """Winery words shared by more than WINERY_WORD_MAX_WINERIES wineries, and
    region words («КУБАНЬ» is not «Кубань-Вино»)."""
    wineries: dict[str, set[str]] = {}
    regions: set[str] = set()
    for winery, region in wineries_and_regions:
        for token in _long_tokens(winery):
            wineries.setdefault(token, set()).add(winery)
        regions |= _long_tokens(region)
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
    label = _long_tokens(ocr_text)
    seen = _seen_tokens(label, names)
    read_winery = ocr_fields.winery[0].value.strip() if ocr_fields.winery else None
    is_winery_shown = bool(read_winery) and _shows(label, _long_tokens(read_winery) - generic_winery)
    category, year = only_value(ocr_fields.category), only_value(ocr_fields.year)
    sweetness = only_value(ocr_fields.sweetness)
    checks = []
    for wine in shortlist:
        read_words = _catalog_words(wine, seen[wine.slug])
        fully = bool(names[wine.slug]) and seen[wine.slug] == names[wine.slug]
        for rival in shortlist:
            if rival.slug == wine.slug:
                continue
            speaks_for_rival = seen[rival.slug] - names[wine.slug]
            speaks_for_wine = seen[wine.slug] - names[rival.slug]
            if speaks_for_rival and not speaks_for_wine:
                words = ", ".join(f"«{word}»" for word in _catalog_words(rival, speaks_for_rival))
                checks.append(LabelCheck(wine.slug, read_words, "name",
                                         f"на этикетке {words} из «{rival.name.strip()}», в этом названии их нет",
                                         fully))
                break
        else:
            wine_year = extract_year(wine.name)
            if (is_winery_shown and wine.winery.strip() != read_winery and not seen[wine.slug]
                    and not _shows(label, _long_tokens(wine.winery) - generic_winery)):
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


def rank(ocr_fields: RetrievalFields, visual_fields: RetrievalFields, wines: list[Wine],
         *, min_margin: float = MIN_MARGIN, ocr_text: str = "") -> RankingResult:
    distributions = _distributions(ocr_fields, visual_fields)
    breakdowns = {wine.slug: _contributions(wine, distributions) for wine in wines}
    evidence = {slug: round(_score(terms), 4) for slug, terms in breakdowns.items()}
    if not distributions or not evidence:
        return RankingResult("not_found", None, 0.0, 0.0, evidence)
    by_slug = {wine.slug: wine for wine in wines}
    order = [slug for slug, _ in _ranked(evidence, len(evidence))]
    shortlist = [by_slug[slug] for slug in order[:VERIFY_SHORTLIST]]
    named = {candidate.value for candidate in ocr_fields.name[:1]}
    shortlist += [wine for wine in wines if wine.name.strip() in named and wine not in shortlist]
    generic_winery = generic_winery_tokens(wines)
    while True:
        checks = verify_shortlist(shortlist, ocr_fields, ocr_text, generic_winery)
        slug, margin, rival = _decide(evidence, order, checks)
        if rival is None or rival in {wine.slug for wine in shortlist} or len(shortlist) >= VERIFY_LIMIT:
            break
        shortlist.append(by_slug[rival])
    rejected = {check.slug: check.reason for check in checks if check.kind}
    score = evidence[slug]
    if len(rejected) == len(checks):
        return RankingResult("not_found", None, score, margin, evidence, rejected, checks)
    is_identified = _is_identified(breakdowns[slug],
                                   next((c for c in checks if c.slug == slug), None) if ocr_text.strip() else None,
                                   _visual_share(visual_fields, slug, rejected))
    if is_identified and margin >= min_margin:
        return RankingResult("matched", slug, score, margin, evidence, rejected, checks)
    return RankingResult("not_found", None, score, margin, evidence, rejected, checks)


def _visual_share(visual_fields: RetrievalFields, slug: str, rejected: dict[str, str]) -> float:
    """The wine's share of the visual field among wines the label does not
    contradict: «Аврора 2024» next to a rejected «Аврора 2023» is the visual match."""
    candidates = tuple(c for c in visual_fields.slug if c.value not in rejected)
    return field_distribution(candidates, VISUAL_TEMPERATURE).get(slug, 0.0) if candidates else 0.0


def _is_identified(terms: tuple[FieldContribution, ...], check: LabelCheck | None, visual: float) -> bool:
    """A clear visual match (``visual`` — _visual_share) identifies a wine; a
    faint one only together with its name. OCR alone does only when the label shows every distinctive word
    of its name. «Пино Нуар полусухое» of one winery is every Pinot Noir
    label: read on a Табия bottle (not in the catalog), it must not match
    Новый Свет's wine of that name. Without label text (``check`` is None)
    there is nothing to check the name against."""
    name = next((term.score for term in terms if term.field == "name"), 0.0)
    if visual >= VISUAL_IDENTIFY_MIN or (visual > 0 and name > 0):
        return True
    return name > 0 and (check is None or check.is_fully_read)


def _decide(evidence: dict[str, float], order: list[str],
            checks: tuple[LabelCheck, ...]) -> tuple[str, float, str | None]:
    """The best checked wine the label does not contradict, its margin, and the runner-up.

    Out of the race: wines the label overturned (they outscored the winner),
    wines that contradict a stated fact, and — when the label spells out the
    winner's whole name — wines it contradicts by name. A name-contradicted
    wine below a winner the label names only in part stays a rival: the label
    may equally fit a sibling nobody checked («Цитрон» of «Пет-Нат
    Цитрон-Ркацители» fits «Петнат Цитрон – Рислинг» as well)."""
    by_slug = {check.slug: check for check in checks}
    winner = next((slug for slug in order if slug in by_slug and not by_slug[slug].kind), order[0])
    score = evidence[winner]
    fully_named = winner in by_slug and by_slug[winner].is_fully_read

    def is_out(slug: str) -> bool:
        check = by_slug.get(slug)
        if check is None or not check.kind:
            return False
        return evidence[slug] > score or check.kind in HARD_CONTRADICTIONS or fully_named

    rival = next((slug for slug in order if slug != winner and not is_out(slug)), None)
    return winner, (round(score - evidence[rival], 4) if rival else score), rival
