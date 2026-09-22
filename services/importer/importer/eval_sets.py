from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath
import zipfile

from .catalog_csv import Issue
from .config import EVAL_ARCHIVES, EVAL_BUCKET
from .storage import ObjectStore


def is_system_entry(name: str) -> bool:
    path = PurePosixPath(name)
    return path.parts[:1] == ("__MACOSX",) or path.name.startswith("._") or path.name == ".DS_Store"


def decoded_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def upload_eval_sets(input_dir: Path, store: ObjectStore) -> tuple[dict[str, int], list[Issue]]:
    uploaded: dict[str, int] = {}
    issues: list[Issue] = []
    for prefix, filename in EVAL_ARCHIVES.items():
        path = input_dir / filename
        if not path.is_file():
            issues.append(Issue("eval_set_missing", None, {"file": filename}))
            continue
        existing = set(store.list_keys(EVAL_BUCKET, f"{prefix}/"))
        count = 0
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = decoded_name(info)
                if info.is_dir() or is_system_entry(name):
                    continue
                key = f"{prefix}/{name}"
                count += 1
                if key in existing:
                    continue
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                store.put_bytes(EVAL_BUCKET, key, archive.read(info), content_type)
        uploaded[prefix] = count
    return uploaded, issues
