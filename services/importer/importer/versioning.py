from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


MAPPING_ALGO_VERSION = "mapping-v2"
PREVIEW_VERSION = "webp-400x600-q80-v1"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True)
class DatasetFingerprint:
    catalog_sha256: str
    archive_sha256: str
    overrides_sha256: str
    mapping_algo_version: str = MAPPING_ALGO_VERSION
    preview_version: str = PREVIEW_VERSION

    @property
    def dataset_version(self) -> str:
        source = "|".join((
            self.catalog_sha256,
            self.archive_sha256,
            self.overrides_sha256,
            self.mapping_algo_version,
            self.preview_version,
        ))
        return hashlib.sha256(source.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_sha256(paths: list[Path]) -> str:
    return hashlib.sha256("".join(file_sha256(path) for path in paths).encode("ascii")).hexdigest()


def optional_file_sha256(path: Path) -> str:
    return file_sha256(path) if path.is_file() else EMPTY_SHA256
