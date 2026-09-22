from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import rarfile


ORIGINAL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DERIVATIVE_PREFIXES = ("thumbnail_", "small_", "medium_", "large_")
UPLOADS_MARKER = "strapi/uploads/"


@dataclass(frozen=True)
class ArchiveMember:
    strapi_path: str
    content: bytes

    @property
    def filename(self) -> str:
        return PurePosixPath(self.strapi_path).name


@dataclass
class ArchiveStats:
    originals: int = 0
    skipped: Counter[str] = field(default_factory=Counter)


def strapi_path_of(archive_path: str) -> str | None:
    normalized = archive_path.replace("\\", "/")
    _, marker, tail = normalized.partition(UPLOADS_MARKER)
    return tail if marker and tail else None


def classify(archive_path: str) -> str:
    strapi_path = strapi_path_of(archive_path)
    if strapi_path is None:
        return "outside_uploads"
    name = PurePosixPath(strapi_path).name
    if name.startswith(DERIVATIVE_PREFIXES):
        return "derivative"
    if PurePosixPath(name).suffix.casefold() not in ORIGINAL_EXTENSIONS:
        return "unsupported_extension"
    return "original"


def iter_originals(first_volume: Path, stats: ArchiveStats) -> Iterator[ArchiveMember]:
    with rarfile.RarFile(first_volume) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            kind = classify(info.filename)
            if kind != "original":
                stats.skipped[kind] += 1
                continue
            stats.originals += 1
            yield ArchiveMember(strapi_path=strapi_path_of(info.filename) or "", content=archive.read(info))
