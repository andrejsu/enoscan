from dataclasses import replace
from io import BytesIO

import numpy as np
from PIL import Image

from app.baseline.service import BaselineSearch
from app.catalog.models import Wine
from app.image_features import decode_image
from app.sift_index import Candidate, SearchResult


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское"):
    return Wine(slug, name, winery)


def test_decode_applies_camera_exif_orientation():
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    assert decode_image(buffer.getvalue()).shape[:2] == (40, 20)


class IndexStub:
    references = []

    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, image, *, limit, visual_limit, extra_slugs=()):
        return SearchResult(self.candidates, 1, 2)


def test_close_candidates_are_not_automatic_match():
    first = Candidate(wine(), 0.8, 18, 10)
    second = replace(first, wine=wine("other", "Другое"), score=0.79)
    result = BaselineSearch(IndexStub([first, second])).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "uncertain"


def test_strong_geometry_alone_is_matched():
    candidate = Candidate(wine(), 0.9, 180, 150)
    result = BaselineSearch(IndexStub([candidate])).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "matched"
    assert result.body["wine"]["slug"] == candidate.wine.slug


def test_catalog_version_comes_from_dataset_version():
    candidate = Candidate(wine(), 0.8, 18, 10)
    result = BaselineSearch(IndexStub([candidate]), dataset_version="abc123").search(
        np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["version"]["catalog"] == "abc123"
