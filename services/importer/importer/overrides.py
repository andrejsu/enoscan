from __future__ import annotations

from collections.abc import Iterable
import csv
from dataclasses import dataclass, replace
from pathlib import Path

from .catalog_csv import Issue
from .mapping import Mapping, SourceImage


ACTIONS = {"set", "reject", "confirm"}
HEADER = ["slug", "action", "strapi_filename", "note"]


@dataclass(frozen=True)
class Override:
    line_no: int
    slug: str
    action: str
    strapi_filename: str | None
    note: str | None


def parse_overrides(rows: Iterable[list[str]]) -> list[Override]:
    iterator = iter(rows)
    header = next(iterator, None)
    if header is None:
        return []
    if [cell.strip() for cell in header] != HEADER:
        raise SystemExit(f"image-overrides.csv line 1: expected header {','.join(HEADER)}")

    overrides: list[Override] = []
    seen: dict[str, int] = {}
    for line_no, row in enumerate(iterator, start=2):
        if not any(cell.strip() for cell in row):
            continue
        cells = [cell.strip() for cell in row] + [""] * (len(HEADER) - len(row))
        slug, action, filename, note = cells[:4]
        if not slug:
            raise SystemExit(f"image-overrides.csv line {line_no}: slug is empty")
        if action not in ACTIONS:
            raise SystemExit(f"image-overrides.csv line {line_no}: unknown action {action!r}")
        if action == "set" and not filename:
            raise SystemExit(f"image-overrides.csv line {line_no}: action set requires strapi_filename")
        if slug in seen:
            raise SystemExit(f"image-overrides.csv line {line_no}: slug {slug} already overridden on line {seen[slug]}")
        seen[slug] = line_no
        overrides.append(Override(line_no, slug, action, filename or None, note or None))
    return overrides


def read_overrides(path: Path) -> list[Override]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return parse_overrides(csv.reader(stream))


def apply_overrides(
    mappings: list[Mapping],
    overrides: list[Override],
    active_slugs: set[str],
    sources: list[SourceImage],
) -> tuple[list[Mapping], list[Issue]]:
    by_filename: dict[str, list[SourceImage]] = {}
    for source in sources:
        by_filename.setdefault(source.filename, []).append(source)

    by_slug = {mapping.slug: mapping for mapping in mappings}
    issues: list[Issue] = []

    for override in overrides:
        if override.slug not in active_slugs:
            raise SystemExit(f"image-overrides.csv line {override.line_no}: unknown or inactive slug {override.slug}")

        if override.action == "reject":
            by_slug.pop(override.slug, None)
            continue

        if override.action == "confirm":
            current = by_slug.get(override.slug)
            if current is None:
                raise SystemExit(
                    f"image-overrides.csv line {override.line_no}: {override.slug} has no automatic image to confirm"
                )
            by_slug[override.slug] = replace(current, review_status="confirmed")
            continue

        candidates = by_filename.get(override.strapi_filename or "", [])
        distinct = {item.image_sha256 for item in candidates}
        if not candidates:
            raise SystemExit(
                f"image-overrides.csv line {override.line_no}: file {override.strapi_filename} is not in the archive"
            )
        if len(distinct) > 1:
            raise SystemExit(
                f"image-overrides.csv line {override.line_no}: file name {override.strapi_filename} is ambiguous"
            )
        source = sorted(candidates, key=lambda item: item.strapi_path)[0]
        for slug, mapping in list(by_slug.items()):
            if slug != override.slug and mapping.image_sha256 == source.image_sha256:
                del by_slug[slug]
                issues.append(Issue("override_displaced", slug, {
                    "strapi_path": mapping.strapi_path,
                    "override_slug": override.slug,
                    "line_no": override.line_no,
                }))
        by_slug[override.slug] = Mapping(
            slug=override.slug,
            image_sha256=source.image_sha256,
            strapi_path=source.strapi_path,
            mapping_kind="manual",
            mapping_score=1.0,
            review_status="confirmed",
        )

    return sorted(by_slug.values(), key=lambda item: item.slug), issues
