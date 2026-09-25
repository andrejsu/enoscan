"""Sugar level of a wine («сухое», «полусладкое», «брют»…), from catalog text or a label.

The catalog has no column for it: it sits in the name («Полусухое Красное»),
the slug (`…-krasnoe-polusuhoe-13`) or only in the source photo's file name
(«Пино Нуар, Мускат п.сл.webp» — three Жемчужная 9 siblings differ in
nothing else). One parser reads all of them and the OCR text, so a label's
«ПОЛУСУХОЕ» and a file's «п.сух» land on the same value.
"""

from __future__ import annotations

import re


DRY, SEMI_DRY, SEMI_SWEET, SWEET = "сухое", "полусухое", "полусладкое", "сладкое"
BRUT, EXTRA_BRUT, BRUT_NATURE = "брют", "экстра брют", "брют натюр"

# Longest first: a matched span is blanked, so «полусухое» never also reads as «сухое».
_PATTERNS = tuple((re.compile(pattern), value) for pattern, value in (
    (r"\b(?:экстра|extra|ekstra) (?:брют|brut|bryut)\b", EXTRA_BRUT),
    (r"\b(?:брют|brut|bryut) (?:натюр|nature|natyur)\b|\bzero dosage\b|\bdosage zero\b|\bpas dos[eé]\b",
     BRUT_NATURE),
    (r"\bполусух\w*|\bп сух\w*|\bpolusuh\w*|\bp suh\w*|\bsemi dry\b|\bdemi sec\b|\bhalbtrocken\b|\babboccato\b",
     SEMI_DRY),
    (r"\bполусладк\w*|\bп сл\b|\bpol[su]*sladk\w*|\bp sl\b|\bsemi sweet\b|\bsemidolce\b|\bamabile\b"
     r"|\bmoelleux\b|\bmoellyo\b|\blieblich\b", SEMI_SWEET),
    (r"\bбрют\b|\bbrut\b|\bbryut\b", BRUT),
    (r"\bсух(?:ое|ой|ая|ие)?\b|\bsuh(?:oe|oy|aya)?\b|\bdry\b|\bsec\b|\bsecco\b|\bseco\b|\btrocken\b", DRY),
    (r"\bсладк(?:ое|ий|ая|ие)\b|\bsladk(?:oe|iy|aya)\b|\bsweet\b|\bdolce\b|\bdoux\b|\bdulce\b", SWEET),
))
_SEPARATORS = re.compile(r"[\s_\-./,;:()«»\"']+")
_BRUT_FAMILY = {BRUT, EXTRA_BRUT, BRUT_NATURE}


def sugar_levels(text: str) -> set[str]:
    """Every sugar level the text names."""
    text = " " + _SEPARATORS.sub(" ", text.casefold().replace("ё", "е")) + " "
    found = set()
    for pattern, value in _PATTERNS:
        if pattern.search(text):
            found.add(value)
            text = pattern.sub(" ", text)
    return found


def sugar_level(text: str) -> str | None:
    """The one sugar level the text names; None when it names none or two
    that disagree. «Игристое брют … экстра брют» is extra brut, not a conflict."""
    found = sugar_levels(text)
    if len(found) > 1 and found <= _BRUT_FAMILY:
        found -= {BRUT}
    return found.pop() if len(found) == 1 else None


def catalog_sugar_level(*sources: str | None) -> str | None:
    """The first source that names exactly one sugar level: name, then slug, then photo file name."""
    for source in sources:
        if source and (level := sugar_level(source)):
            return level
    return None


def contradicts(label: str, catalog: str) -> bool:
    """Different levels, except within the brut family: OCR may read «BRUT» of «EXTRA BRUT»."""
    return label != catalog and not {label, catalog} <= _BRUT_FAMILY
