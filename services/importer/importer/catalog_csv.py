from __future__ import annotations

from collections.abc import Iterable
import csv
from dataclasses import dataclass, field
from pathlib import Path


COLUMNS = {
    "Название вина": "name",
    "Категория": "category",
    "Цвет": "color",
    "Регион": "region",
    "Сорт винограда": "grape_varieties",
    "Описание": "description",
    "Винодельня": "winery",
    "Slug": "slug",
    "Название фото": "source_image_filename",
}


@dataclass(frozen=True)
class CatalogWine:
    slug: str
    name: str | None
    category: str | None
    color: str | None
    region: str | None
    grape_varieties: tuple[str, ...]
    description: str | None
    winery: str | None
    source_image_filename: str | None
    source_row_no: int
    raw_record_count: int


@dataclass(frozen=True)
class Issue:
    kind: str
    slug: str | None
    detail: dict[str, object]


@dataclass
class CatalogParseResult:
    raw_rows: list[tuple[int, dict[str, str | None]]] = field(default_factory=list)
    wines: list[CatalogWine] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def split_grapes(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def parse_rows(rows: Iterable[dict[str, str | None]]) -> CatalogParseResult:
    result = CatalogParseResult()
    first_rows: dict[str, tuple[int, dict[str, str | None]]] = {}
    row_numbers: dict[str, list[int]] = {}
    differing: set[str] = set()

    for row_no, source in enumerate(rows, start=1):
        normalized = {key.strip(): value for key, value in source.items() if key is not None}
        missing = [column for column in COLUMNS if column not in normalized]
        if missing:
            raise SystemExit(f"Catalog CSV is missing columns: {', '.join(missing)}")
        values = {COLUMNS[column]: clean(normalized[column]) for column in COLUMNS}
        result.raw_rows.append((row_no, {column: normalized[column] for column in COLUMNS}))

        slug = values["slug"]
        if slug is None:
            result.issues.append(Issue("missing_slug", None, {"row_no": row_no}))
            continue
        if slug in first_rows:
            row_numbers[slug].append(row_no)
            if first_rows[slug][1] != values:
                differing.add(slug)
            continue
        first_rows[slug] = (row_no, values)
        row_numbers[slug] = [row_no]

    for slug, (row_no, values) in first_rows.items():
        count = len(row_numbers[slug])
        result.wines.append(CatalogWine(
            slug=slug,
            name=values["name"],
            category=values["category"],
            color=values["color"],
            region=values["region"],
            grape_varieties=split_grapes(values["grape_varieties"]),
            description=values["description"],
            winery=values["winery"],
            source_image_filename=values["source_image_filename"],
            source_row_no=row_no,
            raw_record_count=count,
        ))
        if count > 1:
            result.issues.append(Issue("duplicate_slug", slug, {
                "row_numbers": row_numbers[slug],
                "payload_differs": slug in differing,
            }))
    return result


def read_catalog(path: Path) -> CatalogParseResult:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return parse_rows(csv.DictReader(stream))
