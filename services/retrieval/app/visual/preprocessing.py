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
    default as of 2026-09-22) uses the ``fast=True`` fixed-crop path instead.
    SAM stays opt-in, but on 54 real photos (2026-09-27) it ranked the right
    wine lower than the fixed crop — see the retrieval README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
from pathlib import Path

import cv2
import numpy as np


def _import_label_prep():
    try:
        import label_prep
        return label_prep
    except ImportError:
        pass
    for candidate in (
        Path("/app/scripts"),
        Path(__file__).resolve().parents[4] / "scripts",
    ):
        if (candidate / "label_prep.py").is_file():
            sys.path.insert(0, str(candidate))
            import label_prep
            return label_prep
    raise ImportError("Cannot locate label_prep.py; expected at /app/scripts or <repo>/scripts")


label_prep = _import_label_prep()
Config = label_prep.Config
Segmenter = label_prep.Segmenter


@dataclass(frozen=True)
class PreparedQuery:
    visual: np.ndarray
    used_sam: bool
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)
    crop_box: tuple[float, float, float, float] | None = None


FAST_CROP_BOX = (0.05, 0.30, 0.95, 0.95)
# SAM works on a 1024 px copy anyway; a full 12 MP phone frame only makes the
# full-resolution mask decode and the unwrap remap cost ~4 GB and seconds more.
# The visual output is 512 px, so 1600 px leaves the unwrap enough detail.
SAM_INPUT_SIDE = 1600
# Geometry fits on a degenerate mask fail in several ways (empty contour,
# singular polyfit, too-small remap); any of them means "SAM found no usable label".
SAM_FAILURES = (RuntimeError, ValueError, np.linalg.LinAlgError, cv2.error)


def prepare_query(image: np.ndarray, *, segmenter: "Segmenter | None" = None,
                  config: Config | None = None, fast: bool = False) -> PreparedQuery:
    """Normalize a live query photo. ``fast=True`` (or a segmentation failure)
    falls back to a cheap fixed crop instead of raising, so a query that
    defeats SAM still gets *some* answer through raw-image evidence.
    Warnings: ``sam_skipped`` — SAM was not asked for; ``sam_failed`` — it
    was, found no usable label, and the fixed crop answered instead."""
    config = config or Config()
    warning = "sam_skipped"
    if not fast and segmenter is not None:
        try:
            visual, _, meta, _ = label_prep.process(_limit_side(image, SAM_INPUT_SIDE), config,
                                                    segmenter=segmenter, debug_images=False)
            return PreparedQuery(visual, used_sam=True, warnings=meta["warnings"], info=meta["normalize"])
        except SAM_FAILURES:
            warning = "sam_failed"
    visual, info = _fast_crop(image, config)
    return PreparedQuery(visual, used_sam=False, warnings=[warning], info=info, crop_box=FAST_CROP_BOX)


def _limit_side(image: np.ndarray, side: int) -> np.ndarray:
    scale = side / max(image.shape[:2])
    if scale >= 1:
        return image
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def _fast_crop(image: np.ndarray, config: Config) -> tuple[np.ndarray, dict]:
    """No-SAM fallback: bottles are usually held upright with the label in the
    lower-middle third of the frame. Crude but cheap; only used when SAM is
    disabled, unavailable, or fails to find a label. Taller, centered, full-frame
    and two-view variants of this box measured no better on 54 real photos."""
    height, width = image.shape[:2]
    left, top, right, bottom = FAST_CROP_BOX
    crop = image[int(top * height):int(bottom * height), int(left * width):int(right * width)]
    return label_prep.normalize_visual(crop, config)


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
        visual, _, _, _ = label_prep.process(image, config, mask=mask, debug_images=False)
        return visual
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
