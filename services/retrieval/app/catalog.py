from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row


YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
UNKNOWN_NAME = "Без названия"
UNKNOWN_PRODUCER = "Производитель не указан"


@dataclass(frozen=True)
class Wine:
    slug: str
    name: str
    winery: str
    category: str | None = None
    color: str | None = None
    region: str | None = None
    grape_varieties: tuple[str, ...] = ()
    description: str | None = None
    has_image: bool = False

    def as_card(self) -> dict[str, object]:
        year_match = YEAR_PATTERN.search(self.name)
        image_url = f"/api/wines/{quote(self.slug, safe='')}/image" if self.has_image else None
        return {
            "slug": self.slug,
            "name": self.name.strip(),
            "producer": self.winery.strip(),
            "year": int(year_match.group(1)) if year_match else None,
            "category": _optional(self.category),
            "color": _optional(self.color),
            "region": _optional(self.region),
            "grapeVarieties": [item for item in self.grape_varieties if item.strip()],
            "description": _optional(self.description),
            "servingTemperature": None,
            "imageUrl": image_url,
            "imagePreviewUrl": f"{image_url}?size=preview" if image_url else None,
        }

    def field_values(self, field: str) -> list[str]:
        if field == "grape_varieties":
            return [item.strip() for item in self.grape_varieties if item.strip()]
        raw = getattr(self, field)
        return [raw.strip()] if raw else []

    def to_json(self) -> dict[str, object]:
        return {**self.__dict__, "grape_varieties": list(self.grape_varieties)}

    @classmethod
    def from_json(cls, value: dict[str, object]) -> "Wine":
        grapes = value.get("grape_varieties") or ()
        return cls(**{**value, "grape_varieties": tuple(grapes)})


@dataclass(frozen=True)
class Reference:
    wine: Wine
    image_sha256: str
    object_key: str
    mapping_kind: str
    mapping_score: float


def _optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


WINE_COLUMNS = """
  w.slug, w.name, w.winery, w.category, w.color, w.region, w.grape_varieties, w.description
"""


def _wine(row: dict[str, object], has_image: bool) -> Wine:
    return Wine(
        slug=str(row["slug"]),
        name=str(row["name"] or UNKNOWN_NAME),
        winery=str(row["winery"] or UNKNOWN_PRODUCER),
        category=row["category"],
        color=row["color"],
        region=row["region"],
        grape_varieties=tuple(row["grape_varieties"] or ()),
        description=row["description"],
        has_image=has_image,
    )


def current_dataset_version(database_url: str) -> str:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            "SELECT dataset_version FROM import_runs WHERE status = 'succeeded' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("No successful dataset import found. Run the importer first.")
    return str(row[0])


def load_wines(database_url: str) -> list[Wine]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            f"""
            SELECT {WINE_COLUMNS}, wi.slug IS NOT NULL AS has_image
            FROM wines w
            LEFT JOIN wine_images wi ON wi.slug = w.slug AND wi.is_primary
            WHERE w.is_active
            ORDER BY w.slug
            """
        ).fetchall()
    return [_wine(row, bool(row["has_image"])) for row in rows]


def load_references(database_url: str) -> list[Reference]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            f"""
            SELECT {WINE_COLUMNS}, wi.image_sha256, i.object_key, wi.mapping_kind, wi.mapping_score
            FROM wine_images wi
            JOIN wines w ON w.slug = wi.slug AND w.is_active
            JOIN images i ON i.sha256 = wi.image_sha256
            WHERE wi.is_primary
            ORDER BY w.slug
            """
        ).fetchall()
    return [
        Reference(
            wine=_wine(row, True),
            image_sha256=str(row["image_sha256"]),
            object_key=str(row["object_key"]),
            mapping_kind=str(row["mapping_kind"]),
            mapping_score=float(row["mapping_score"]),
        )
        for row in rows
    ]
