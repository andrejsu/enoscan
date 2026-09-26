from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote


YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


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
    sweetness: str | None = None

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
