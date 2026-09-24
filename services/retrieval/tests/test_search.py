from dataclasses import replace
from io import BytesIO
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.catalog import Wine
from app.index import Candidate, SearchResult
from app.ocr import OcrWord, extract_abv_candidates, extract_label, extract_year_candidates, fold_homoglyphs
from app.service import SearchService
from app.text_search import TextSearch
from app.image_features import decode_image


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское"):
    return Wine(slug, name, winery)


def word(text, confidence=90, line=(1, 1, 1)):
    return OcrWord(text, confidence, (0, 0, 80, 20), line)


@pytest.mark.parametrize("text,years,abvs", [
    ("Урожай 2019 12,5 %", ["2019"], ["12.5"]),
    ("Основано в 2019", [], []),
    ("2019", [], []),
    ("0,75 л", [], []),
    ("alc 13.5", [], ["13.5"]),
    ("2019 розлив урожай", [], []),
])
def test_fields_need_context(text, years, abvs):
    assert [c.value for c in extract_year_candidates([word(text)])] == years
    assert [c.value for c in extract_abv_candidates([word(text)])] == abvs


def test_low_confidence_year_abstains():
    assert extract_year_candidates([word("Урожай 2019", confidence=25)]) == ()


@pytest.mark.parametrize("text,expected", [
    ("KPACHOE", "KPACHOE КРАСНОЕ"),       # all look-alikes: keep both readings
    ("ДЕHИCOB", "ДЕНИСОВ"),               # mixed script: Cyrillic wins
    ("3АKAT", "ЗАКАТ"),
    ("3AKAT", "3AKAT ЗАКАТ"),
    ("KOKUR", "KOKUR"),                   # U, R have no Cyrillic twin: real Latin
    ("Урожай 2023г", "Урожай 2023г"),     # digits stay digits
    ("Merlot", "Merlot"),
])
def test_homoglyphs_fold_to_cyrillic(text, expected):
    assert fold_homoglyphs(text) == expected


class EngineResult:
    boxes = [[[10, 20], [110, 22], [110, 60], [10, 58]]]
    txts = ("Усадьба Перавских KPACHOE",)
    scores = (0.93,)


def test_engine_lines_become_words_with_bbox_and_percent_confidence():
    with patch("app.ocr.load_engine", return_value=lambda image: EngineResult()):
        result = extract_label(np.zeros((100, 200, 3), dtype=np.uint8))
    assert result.words == (OcrWord("Усадьба Перавских KPACHOE КРАСНОЕ", 93.0, (10, 20, 100, 40), (1, 1, 1)),)


def test_no_text_found_is_an_empty_result():
    empty = type("Empty", (), {"boxes": None, "txts": None, "scores": None})()
    with patch("app.ocr.load_engine", return_value=lambda image: empty):
        assert extract_label(np.zeros((10, 10, 3), dtype=np.uint8)).words == ()


def test_decode_applies_camera_exif_orientation():
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    assert decode_image(buffer.getvalue()).shape[:2] == (40, 20)


def test_text_search_ignores_generic_words_and_numbers():
    search = TextSearch([wine(), wine("other", "Кокур 2020", "Табия")])
    assert search.scores("вино wine 2019") == {}
    assert search.candidates(search.scores("Ребус Дивноморское"), 5)[0].slug == "rebus-2019"


def test_same_observed_words_do_not_prefer_shorter_title():
    search = TextSearch([wine("long", "Декантер Каберне Фран", "Фанагория"),
                         wine("short", "Декантер Мерло", "Фанагория")])
    scores = search.scores("Фанагория Декантер")
    assert scores["long"] == scores["short"]


class IndexStub:
    references = []

    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, image, *, limit, visual_limit, extra_slugs=()):
        return SearchResult(self.candidates, 1, 2)


def test_close_candidates_are_not_automatic_match():
    first = Candidate(wine(), "a.jpg", 0.8, 18, 10)
    second = replace(first, wine=wine("other", "Другое"), score=0.79)
    result = SearchService(IndexStub([first, second])).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "uncertain"


def test_strong_geometry_alone_is_matched():
    candidate = Candidate(wine(), "a.jpg", 0.9, 180, 150)
    result = SearchService(IndexStub([candidate])).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "matched"
    assert result.body["wine"]["slug"] == candidate.wine.slug


def test_catalog_version_comes_from_dataset_version():
    candidate = Candidate(wine(), "sha", 0.8, 18, 10)
    result = SearchService(IndexStub([candidate]), dataset_version="abc123").search(
        np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["version"]["catalog"] == "abc123"
