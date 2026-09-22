from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import PurePosixPath
import re
import unicodedata

from .catalog_csv import CatalogWine


HASH_SUFFIX = re.compile(r"_[0-9a-f]{10}$", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
FUZZY_THRESHOLD = 0.72
SUSPICIOUS_FUZZY_SCORE = 0.85
GENERIC_TOKENS = {
    "beloe", "butylka", "etiketka", "foto", "igristoe", "krasnoe",
    "normal", "photo", "preview", "rozovoe", "suhoe", "vino", "wine",
    "winery",
}

CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


@dataclass(frozen=True)
class SourceImage:
    strapi_path: str
    filename: str
    image_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Mapping:
    slug: str
    image_sha256: str
    strapi_path: str
    mapping_kind: str
    mapping_score: float
    review_status: str = "auto"




def _stem(filename: str) -> str:
    return PurePosixPath(filename).stem


def normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def latin_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold().translate(CYRILLIC_TO_LATIN)
    return {
        token
        for token in TOKEN_PATTERN.findall(normalized)
        if len(token) >= 3 and not token.isdigit() and token not in GENERIC_TOKENS
    }


def media_stem(filename: str) -> str:
    return HASH_SUFFIX.sub("", _stem(filename))


def token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if min(len(left), len(right)) < 5:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _catalog_words(wine: CatalogWine) -> set[str]:
    return latin_tokens(
        f"{wine.slug} {_stem(wine.source_image_filename or '')} {wine.name or ''} {wine.winery or ''}"
    )


def fuzzy_score(catalog_words: set[str], media_words: set[str]) -> float:
    if not media_words or not catalog_words:
        return 0.0

    matches = 0.0
    for media_word in media_words:
        best = max((token_similarity(media_word, catalog_word) for catalog_word in catalog_words), default=0.0)
        if best >= 0.82:
            matches += best

    coverage = matches / len(media_words)
    precision = matches / len(catalog_words)
    return (0.8 * coverage) + (0.2 * precision)


def resolve_mappings(wines: list[CatalogWine], sources: list[SourceImage]) -> list[Mapping]:
    by_key: dict[str, list[SourceImage]] = {}
    for item in sources:
        by_key.setdefault(normalize_key(media_stem(item.filename)), []).append(item)

    mappings: list[Mapping] = []
    used: set[str] = set()
    unresolved: list[CatalogWine] = []

    for wine in sorted(wines, key=lambda item: item.slug):
        image_matches = by_key.get(normalize_key(_stem(wine.source_image_filename or "")), []) \
            if wine.source_image_filename else []
        slug_matches = by_key.get(normalize_key(wine.slug), [])
        matches = image_matches or slug_matches
        if not matches:
            unresolved.append(wine)
            continue

        selected = max(matches, key=lambda item: (item.size_bytes, item.strapi_path))
        used.add(selected.image_sha256)
        mappings.append(Mapping(
            slug=wine.slug,
            image_sha256=selected.image_sha256,
            strapi_path=selected.strapi_path,
            mapping_kind="image_filename" if image_matches else "slug",
            mapping_score=1.0,
        ))

    available = [item for item in sources if item.image_sha256 not in used]
    media_tokens = {item.strapi_path: latin_tokens(media_stem(item.filename)) for item in available}
    paths_by_token: dict[str, set[str]] = {}
    for path, tokens in media_tokens.items():
        for token in tokens:
            paths_by_token.setdefault(token, set()).add(path)
    source_by_path = {item.strapi_path: item for item in available}

    for wine in unresolved:
        catalog_words = _catalog_words(wine)
        candidate_paths: set[str] = set()
        for token in catalog_words:
            candidate_paths.update(paths_by_token.get(token, set()))
        candidates = [
            source_by_path[path]
            for path in sorted(candidate_paths)
            if source_by_path[path].image_sha256 not in used
        ]
        scored = sorted(
            ((fuzzy_score(catalog_words, media_tokens[item.strapi_path]), item) for item in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not scored or scored[0][0] < FUZZY_THRESHOLD:
            continue

        score, selected = scored[0]
        used.add(selected.image_sha256)
        mappings.append(Mapping(
            slug=wine.slug,
            image_sha256=selected.image_sha256,
            strapi_path=selected.strapi_path,
            mapping_kind="fuzzy_filename",
            mapping_score=score,
        ))

    return mappings


def shared_images(mappings: list[Mapping]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for mapping in mappings:
        owners.setdefault(mapping.image_sha256, []).append(mapping.slug)
    return {sha: sorted(slugs) for sha, slugs in owners.items() if len(slugs) > 1}


def mark_suspicious(mappings: list[Mapping]) -> list[Mapping]:
    shared = shared_images(mappings)
    return [
        replace(mapping, review_status="suspicious")
        if mapping.review_status == "auto" and (
            mapping.image_sha256 in shared
            or (mapping.mapping_kind == "fuzzy_filename" and mapping.mapping_score < SUSPICIOUS_FUZZY_SCORE)
        )
        else mapping
        for mapping in mappings
    ]
