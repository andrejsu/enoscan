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
from math import exp

from .catalog import Wine
from .label_fields import FieldCandidate, RetrievalFields
from .ocr.constants import FUZZY_MIN_LENGTH, TOKEN_MATCH_SIMILARITY
from .ocr.fields import extract_year
from .ocr.tokens import token_similarity, tokenize
from .sweetness import contradicts as sugar_contradicts


# Relative importance; scores are divided by their fixed sum. Absent on
# purpose: `abv` — catalog.Wine has no ABV column to match; `sweetness` —
# siblings of one label differ in it and nothing else, so it decides as a
# contradiction in verify_shortlist rather than as a vote shared by every
# «сухое» of the catalog.
# Tuned 2026-09-25 on 156 queries (9 real photos + 147 hard augmentations of
# catalog images, see scripts/README.md); held on both halves of the set.
# Still a small sample — revisit with more real photos.
FIELD_WEIGHTS = {
    "slug": 0.70, "name": 0.20, "winery": 0.20, "grape_varieties": 0.12,
    "year": 0.08, "region": 0.04, "category": 0.03,
}
TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())

# Softmax temperature per source, in raw-score units: how far below the
# field's top-1 a candidate may sit and still share its probability.
# Visual scores bunch within ~0.1 of each other, OCR ones spread wider.
VISUAL_TEMPERATURE = 0.05
OCR_TEMPERATURE = 0.06

# Minimum top-1 minus top-2 score for `matched`. Lowered from 0.06 to 0.03 on
# 2026-09-25 by product decision, to answer more photos without the choice
# screen. Measured on the bench (10 real photos + 147 hard augmentations,
# after the label check): the real photos stayed 7 right / 0 wrong at both
# values, the augmentations went 89 right / 14 wrong -> 90 right / 28 wrong
# (F1 0.712 -> 0.679). The closest out-of-catalog photo sits at 0.025: 0.02
# already answers it wrongly.
MIN_MARGIN = 0.03

# Only the visual match and the name can pin down one wine (_is_identified).
# The rest (winery, grape, category, region, year, sweetness) are shared by many
# wines: OCR reading only "Красное" must never match whichever red wine
# comes first. Those fields may still rank, never match alone.

# Fields that only confirm a wine whose name OCR read on the label. A
# label's «2022» is one of hundreds of «… 2022» names in the catalog:
# counted for all of them, it pushed wines with no other evidence into the
# top-5, and a faint visual match («Аврора 2024», 10 inliers) took the full
# year credit next to the wine the label actually names.
CONFIRMING_FIELDS = ("year",)

# How many of the ranking's top wines are checked against the label. Near
# twins (one line, several cuvées) sit within the visual top-3. The
# runner-up is checked as well, down the ranking up to VERIFY_LIMIT wines.
VERIFY_SHORTLIST = 3
VERIFY_LIMIT = 8

# Style words the catalog puts into some names and not others («Экстра
# брют» on the label, bare «Кюве Александр» in the catalog): never evidence
# that the label names another wine.
STYLE_WORDS = "брют brut экстра extra резерв reserve riserva сухое полусухое полусладкое сладкое классик classic"

# A category, year or sugar level the label states is a fact, so a wine it
# contradicts leaves the race. A name contradiction is softer (OCR may have missed this
# wine's words): the wine only drops below the rest and still counts as the
# runner-up of any wine below it.
HARD_CONTRADICTIONS = ("category", "year", "sweetness")


@dataclass(frozen=True)
class RankingResult:
    status: str  # "matched" | "not_found"
    slug: str | None  # set only when matched
    score: float  # top-1 wine's score, whether or not it matched
    margin: float  # top-1 minus top-2 score, among wines the label does not contradict
    evidence: dict[str, float]  # every catalog slug's score, for inspection
    rejected: dict[str, str] = field(default_factory=dict)  # slug -> why the label contradicts it
    checks: tuple["LabelCheck", ...] = ()  # the shortlist as verify_shortlist saw it, in ranking order

    def ranked(self, limit: int) -> list[tuple[str, float]]:
        return _ranked(self.evidence, limit, self.rejected)


def _ranked(evidence: dict[str, float], limit: int,
            rejected: dict[str, str] | None = None) -> list[tuple[str, float]]:
    # Rejected wines go last; slug breaks score ties, so equal evidence never
    # depends on catalog order.
    rejected = rejected or {}
    return sorted(evidence.items(), key=lambda item: (item[0] in rejected, -item[1], item[0]))[:limit]


@dataclass(frozen=True)
class FieldContribution:
    field: str
    weight: float
    score: float  # this wine's probability within the field, 0 when absent


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
    read_words: tuple[str, ...]  # words of its catalog name the label shows, as the catalog spells them
    kind: str | None = None  # "name" | "category" | "year" | "sweetness" when the label contradicts the wine
    reason: str | None = None  # human-readable, for the debug panel
    is_fully_read: bool = False  # the label shows every distinctive word of its name


def _catalog_words(wine: Wine, tokens: set[str]) -> tuple[str, ...]:
    """The words of the wine's name that carry these tokens, in catalog spelling."""
    words = []
    for word in wine.name.replace("-", " ").split():
        if _long_tokens(word) & tokens and word.strip(".,«»\"()") not in words:
            words.append(word.strip(".,«»\"()"))
    return tuple(words)


def verify_shortlist(shortlist: list[Wine], ocr_fields: RetrievalFields, ocr_text: str) -> tuple[LabelCheck, ...]:
    """Check each shortlisted wine against what OCR read.

    A name contradicts a wine only when the label shows a long word of a
    rival's name that this wine's name lacks, while nothing on the label
    speaks for this wine over that rival. Short or shared words (a line name,
    «Пет-Нат») never do: they fit every sibling equally. A category, year or
    sugar level contradicts only when OCR read exactly one and the wine has
    another («РОЗОВОЕ ПОЛУСУХОЕ» against its «сухое» and «полусладкое» twins)."""
    names = {wine.slug: _name_tokens(wine) for wine in shortlist}
    seen = _seen_tokens(_long_tokens(ocr_text), names)
    category, year = only_value(ocr_fields.category), only_value(ocr_fields.year)
    sweetness = only_value(ocr_fields.sweetness)
    checks = []
    for wine in shortlist:
        read_words = _catalog_words(wine, seen[wine.slug])
        fully = bool(names[wine.slug]) and seen[wine.slug] == names[wine.slug]
        for rival in shortlist:
            if rival.slug == wine.slug:
                continue
            # Catalog names are exact spellings: «Мускат» and «Мускатель» are two words here.
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
            if category and wine.category and wine.category.strip() != category:
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
    # The name OCR read best is checked too, even when visual evidence left it
    # outside the top: each block may put a wine forward, the label decides.
    named = {candidate.value for candidate in ocr_fields.name[:1]}
    shortlist += [wine for wine in wines if wine.name.strip() in named and wine not in shortlist]
    while True:
        checks = verify_shortlist(shortlist, ocr_fields, ocr_text)
        slug, margin, rival = _decide(evidence, order, checks)
        # The runner-up the margin is measured against must face the label too.
        if rival is None or rival in {wine.slug for wine in shortlist} or len(shortlist) >= VERIFY_LIMIT:
            break
        shortlist.append(by_slug[rival])
    rejected = {check.slug: check.reason for check in checks if check.kind}
    score = evidence[slug]
    if len(rejected) == len(checks):
        # The label contradicts every checked wine: an honest not_found, not a
        # guess from further down the list.
        return RankingResult("not_found", None, score, margin, evidence, rejected, checks)
    is_identified = _is_identified(breakdowns[slug],
                                   next((c for c in checks if c.slug == slug), None) if ocr_text.strip() else None)
    if is_identified and margin >= min_margin:
        return RankingResult("matched", slug, score, margin, evidence, rejected, checks)
    return RankingResult("not_found", None, score, margin, evidence, rejected, checks)


def _is_identified(terms: tuple[FieldContribution, ...], check: LabelCheck | None) -> bool:
    """A visual match identifies a wine; OCR alone does only when the label
    shows every distinctive word of its name. «Пино Нуар полусухое» of one
    winery is every Pinot Noir label: read on a Табия bottle (not in the
    catalog), it must not match Новый Свет's wine of that name. Without label
    text (``check`` is None) there is nothing to check the name against."""
    scores = {term.field: term.score for term in terms}
    if scores.get("slug", 0) > 0:
        return True
    return scores.get("name", 0) > 0 and (check is None or check.is_fully_read)


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
