"""Download the pinned public DINOv2 ONNX checkpoint into the model volume."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import urllib.request


MODEL_URL = "https://huggingface.co/onnx-community/dinov2-small-ONNX/resolve/main/onnx/model.onnx"
MODEL_SHA256 = "6266c3cd72db6953cecdcbfeab9422a9f783d96f1a4e296ba70ffbac43b54a18"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    destination = Path(os.environ.get("MODEL_PATH", "/models/dinov2-small.onnx"))
    if destination.is_file() and digest(destination) == MODEL_SHA256:
        print(f"Model verified: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    print(f"Downloading {MODEL_URL}", flush=True)
    urllib.request.urlretrieve(MODEL_URL, temporary)
    if digest(temporary) != MODEL_SHA256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("DINOv2 model checksum mismatch")
    temporary.replace(destination)
    print(f"Model verified: {destination}")


if __name__ == "__main__":
    main()
