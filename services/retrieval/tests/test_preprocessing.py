import numpy as np
import pytest

pytest.importorskip("label_prep")

from app.visual.preprocessing import (
    FAST_CROP_BOX,
    SAM_INPUT_SIDE,
    Config,
    label_prep,
    prepare_query,
)


def photo(height=4032, width=3024, seed=3):
    """A phone-sized frame: noisy background with a flat, text-like label."""
    rng = np.random.default_rng(seed)
    image = rng.normal(90, 12, (height, width, 3)).clip(0, 255).astype(np.uint8)
    image[height // 3:height * 5 // 6, width // 4:width * 3 // 4] = 235
    for row in range(height // 3 + 60, height * 5 // 6 - 60, 90):
        image[row:row + 25, width // 4 + 80:width * 3 // 4 - 80] = 30
    return image


class FailingSegmenter:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.shapes: list[tuple[int, ...]] = []

    def segment(self, image, roi=None):
        self.shapes.append(image.shape)
        raise self.error


def test_fast_query_is_the_fixed_crop_at_visual_size():
    prepared = prepare_query(photo(), fast=True)
    assert prepared.used_sam is False
    assert prepared.warnings == ["sam_skipped"]
    assert prepared.crop_box == FAST_CROP_BOX
    assert max(prepared.visual.shape[:2]) == Config().visual_size
    assert set(prepared.info) >= {"label_px", "noise_sigma", "sharpness", "glare_frac"}


def test_visual_normalization_matches_the_full_one_it_replaces():
    crop = photo(1200, 900)
    fast, _ = label_prep.normalize_visual(crop, Config())
    full = label_prep.normalize(crop, Config())[0]
    assert fast.shape == full.shape
    assert np.abs(fast.astype(np.int16) - full.astype(np.int16)).mean() < 4


def test_small_label_is_upscaled_no_more_than_max_upscale():
    visual, info = label_prep.normalize_visual(photo(100, 80), Config())
    assert max(visual.shape[:2]) == 200
    assert info["label_px"] == [80, 100]


@pytest.mark.parametrize("error", [RuntimeError("no label"), ValueError("empty contour"),
                                   np.linalg.LinAlgError("singular")])
def test_sam_failure_falls_back_to_the_fixed_crop(error):
    segmenter = FailingSegmenter(error)
    prepared = prepare_query(photo(), segmenter=segmenter)
    assert prepared.used_sam is False
    assert prepared.warnings == ["sam_failed"]
    assert prepared.crop_box == FAST_CROP_BOX
    assert max(segmenter.shapes[0][:2]) == SAM_INPUT_SIDE


def test_process_skips_debug_frames_for_the_service():
    image = photo(800, 600)
    mask = np.zeros(image.shape[:2], dtype=bool)
    mask[image.shape[0] // 3:image.shape[0] * 5 // 6, image.shape[1] // 4:image.shape[1] * 3 // 4] = True
    visual, _, _, debug = label_prep.process(image, Config(), mask=mask, debug_images=False)
    assert debug == {}
    assert max(visual.shape[:2]) == Config().visual_size
