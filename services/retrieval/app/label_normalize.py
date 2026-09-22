"""Bridge to scripts/label_prep.py: normalize both catalog art and query photos
onto the same canonical "flat label" view before SIFT/embedding comparison.

Two paths, because they see very different input:
  * ``prepare_reference_image`` — catalog art. Usually a clean studio photo, often with
    a transparent background. No SAM call: an alpha-channel/bottle-crop heuristic
    is enough, and skipping SAM keeps a full-catalog rebuild in the minutes range
    instead of hours (SAM ViT-B costs ~8-12s/image on this hardware, see the
    retrieval README benchmark note).
  * ``prepare_query`` — a real phone photo of a bottle: tilted, curved label,
    cluttered background. label_prep.py's SAM segmentation and cylinder-unwarp
    were built for exactly this, but at ~8-12s/photo it blows a real search
    budget (measured end-to-end target: ~3s). ``QUERY_SAM=false`` (the
    default as of 2026-09-22) uses the ``fast=True`` center-crop path instead;
    SAM stays available as an opt-in slow-but-thorough mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
from pathlib import Path

import cv2
import numpy as np


def _import_label_prep():
    try:
        import label_prep  # noqa: F401
        return label_prep
    except ImportError:
        pass
    for candidate in (
        Path("/app/scripts"),  # container: Dockerfile copies scripts/label_prep.py here
        Path(__file__).resolve().parents[3] / "scripts",  # repo checkout: <repo>/scripts
    ):
        if (candidate / "label_prep.py").is_file():
            sys.path.insert(0, str(candidate))
            import label_prep  # noqa: F401
            return label_prep
    raise ImportError("Cannot locate label_prep.py; expected at /app/scripts or <repo>/scripts")


label_prep = _import_label_prep()
Config = label_prep.Config
Segmenter = label_prep.Segmenter


@dataclass(frozen=True)
class PreparedQuery:
    visual: np.ndarray   # color-preserving crop, for SIFT + DINOv2
    ocr: np.ndarray      # grayscale+CLAHE+deglare (used_sam) or plain BGR crop (fast path)
    used_sam: bool
    warnings: list[str] = field(default_factory=list)


def prepare_query(image: np.ndarray, *, segmenter: "Segmenter | None" = None,
                  config: Config | None = None, fast: bool = False) -> PreparedQuery:
    """Normalize a live query photo. ``fast=True`` (or a segmentation failure)
    falls back to a cheap center-crop instead of raising, so a query that
    defeats SAM still gets *some* answer through raw-image evidence."""
    config = config or Config()
    if not fast and segmenter is not None:
        try:
            visual, ocr, _, _ = label_prep.process(image, config, segmenter=segmenter)
            return PreparedQuery(visual, ocr, used_sam=True)
        except RuntimeError:
            pass  # label not found / too small: fall through to the cheap crop
    return PreparedQuery(*_fast_crop(image, config), used_sam=False,
                         warnings=["sam_skipped"])


def _fast_crop(image: np.ndarray, config: Config) -> tuple[np.ndarray, np.ndarray]:
    """No-SAM fallback: bottles are usually held upright with the label in the
    lower-middle third of the frame. Crude but cheap; only used when SAM is
    disabled, unavailable, or fails to find a label.

    The OCR branch hands back the plain BGR crop, not label_prep.normalize's
    grayscale/CLAHE/deglare "ocr" output: that branch upscales to
    cfg.ocr_height (1024 by default) regardless of whether SAM ran, and on
    real photos that alone pushed Tesseract past a 2s budget (measured
    2026-09-22: abrau-dyurso and perovskih both silently lost their OCR
    signal to timeout). ocr.py's own preprocessing on this smaller crop is
    the same fast path the service used before SAM was wired in."""
    height, width = image.shape[:2]
    crop = image[int(0.30 * height):int(0.95 * height), int(0.05 * width):int(0.95 * width)]
    visual, _, _ = label_prep.normalize(crop, config)
    return visual, crop


def reference_label_mask(image: np.ndarray) -> np.ndarray | None:
    """Locate the horizontal label band on a transparent catalog bottle cutout."""
    if image.ndim != 3 or image.shape[2] != 4:
        return None
    height, width = image.shape[:2]
    alpha = image[:, :, 3] > 127
    if alpha.mean() < 0.08:
        return None
    gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    xs = np.flatnonzero(alpha[int(0.7 * height)])
    if len(xs) < width * 0.25:
        return None
    left, right = int(xs.min()), int(xs.max())
    margin = max(2, (right - left) // 5)
    center = gray[:, left + margin:right - margin]
    if center.shape[1] < 8:
        return None
    values = np.median(center, axis=1).astype(np.float32)
    smooth = cv2.GaussianBlur(values[:, None], (1, 0), 5).ravel()
    change = np.diff(smooth)
    start, stop = int(0.35 * height), int(0.85 * height)
    top = start + int(np.argmax(change[start:stop]))
    bottom_start = min(height - 2, top + int(0.15 * height))
    bottom_stop = int(0.99 * height)
    if bottom_start >= bottom_stop:
        return None
    bottom = bottom_start + int(np.argmin(change[bottom_start:bottom_stop]))
    if change[top] < 7 or change[bottom] > -10 or bottom - top < height * 0.15:
        return None
    mask = np.zeros((height, width), dtype=bool)
    mask[top:bottom + 1, left:right + 1] = True
    return mask


def decode_reference_unchanged(content: bytes, name: str) -> np.ndarray:
    source = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if source is None:
        raise ValueError(f"Cannot read image: {name}")
    return source


def prepare_reference_image(source: np.ndarray, *, config: Config | None = None) -> np.ndarray:
    """Normalize a decoded catalog image, using its alpha channel when available. No SAM."""
    config = config or Config()
    has_alpha = source.ndim == 3 and source.shape[2] == 4
    mask = reference_label_mask(source) if has_alpha else None
    if has_alpha:
        alpha = source[:, :, 3:4].astype(np.float32) / 255.0
        image = np.rint(source[:, :, :3] * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    else:
        image = source[:, :, :3] if source.ndim == 3 else cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
    if mask is not None:
        visual, _, _, _ = label_prep.process(image, config, mask=mask)
        return visual
    # No usable alpha band: a broad bottle-body crop keeps the image searchable
    # without guessing at label edges that aren't there.
    height, width = image.shape[:2]
    if has_alpha:
        opaque = source[:, :, 3] > 127
        row = opaque[int(0.7 * height)]
        xs = np.flatnonzero(row)
        left, right = (int(xs.min()), int(xs.max()) + 1) if len(xs) else (0, width)
    else:
        left, right = 0, width
    crop = image[int(0.42 * height):int(0.97 * height), left:right]
    return label_prep.normalize(crop, config)[0]
