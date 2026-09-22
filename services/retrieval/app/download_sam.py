"""Pre-fetch the SAM segmentation model used by label_normalize's query path.

Segmenter() downloads it lazily on first use anyway (see label_prep.ensure_sam),
but that means the first real search after a cold start pays a ~210MB download on
top of the usual SAM latency. Running this in a one-shot compose step keeps that
off the request path.
"""

from __future__ import annotations

import os
from pathlib import Path

from .label_normalize import label_prep


def main() -> None:
    model_dir = Path(os.environ.get("SAM_MODEL_DIR", "/models/sam_vit_b_quant"))
    encoder, decoder = label_prep.ensure_sam(model_dir)
    if not encoder or not decoder:
        raise RuntimeError("SAM encoder or decoder is missing")
    print(f"SAM models ready: {encoder}, {decoder}")


if __name__ == "__main__":
    main()
