from dataclasses import replace
from io import BytesIO
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.catalog import Wine
from app.index import Candidate, SearchResult
from app.ocr import LabelField, OcrResult, OcrWord, extract_fields, extract_label
from app.service import SearchService
from app.text_search import TextSearch
from app.image_features import decode_image


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское"):
    return Wine(slug, name, winery, "test.jpg")


def word(text, confidence=90, line=(1, 1, 1)):
    return OcrWord(text, confidence, (0, 0, 80, 20), line)


@pytest.mark.parametrize("text,year,abv", [
    ("Урожай 2019 12,5 %", 2019, 12.5),
    ("Основано в 2019", None, None),
    ("2019", None, None),
    ("Урожай 2019 или 2020", None, None),
    ("0,75 л", None, None),
    ("alc 13.5", None, 13.5),
    ("2019 розлив урожай", None, None),
    ("12 % 14 %", None, None),
])
def test_fields_need_context(text, year, abv):
    actual_year, actual_abv = extract_fields([word(text)])
    assert (actual_year.value if actual_year else None) == year
    assert (actual_abv.value if actual_abv else None) == abv


def test_low_confidence_year_abstains():
    assert extract_fields([word("Урожай 2019", confidence=25)]) == (None, None)


def test_timeout_falls_back_but_programming_error_propagates():
    image = np.zeros((40, 40, 3), dtype=np.uint8)
    with patch("app.ocr.pytesseract.image_to_data", side_effect=RuntimeError("Tesseract process timeout")):
        assert extract_label(image).error == "timeout"
    with patch("app.ocr.pytesseract.image_to_data", side_effect=ValueError("bug")):
        with pytest.raises(ValueError, match="bug"):
            extract_label(image)


def test_coordinates_return_to_original_image():
    data = {"text": ["Ребус"], "conf": [90], "left": [10], "top": [20],
            "width": [30], "height": [40], "block_num": [1], "par_num": [1], "line_num": [1]}
    with patch("app.ocr.pytesseract.image_to_data", return_value=data):
        result = extract_label(np.zeros((2800, 100, 3), dtype=np.uint8))
    assert result.words[0].bbox == (20, 40, 60, 80)


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


def test_two_reliable_different_vintages_abstain():
    words = [word("Урожай 2019"), word("Урожай 2020", line=(1, 1, 2))]
    assert extract_fields(words)[0] is None


def test_retry_is_bounded_and_keeps_first_pass_on_timeout():
    words = [word("Урожай 2019", confidence=55)]
    with patch("app.ocr._read_words", side_effect=[(words, None), ([], "timeout")]) as read:
        label = extract_label(np.zeros((100, 100, 3), dtype=np.uint8), retry=True, timeout=1)
    assert read.call_count == 2
    assert 0 < read.call_args.args[1] <= 1
    assert label.words == tuple(words)
    assert label.error == "timeout"


class IndexStub:
    references = []

    def __init__(self, candidates):
        self.candidates = candidates
        self.extra_slugs = ()

    def search(self, image, *, limit, extra_slugs, visual_limit):
        self.extra_slugs = extra_slugs
        return SearchResult(self.candidates, 1, 2)


def test_text_adds_wine_without_reference_as_uncertain():
    target = wine()
    index = IndexStub([])
    service = SearchService(index, catalog=[target])
    with patch("app.service.extract_label", return_value=OcrResult((word("Ребус Дивноморское"),))):
        result = service.search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert target.slug in index.extra_slugs
    assert result.body["status"] == "uncertain"
    assert result.body["wine"] is None
    assert result.body["candidates"][0]["wine"]["imageUrl"] is None


def test_wrong_year_does_not_remove_visual_candidate():
    correct = wine()
    other = wine("rebus-2020", "Ребус 2020")
    index = IndexStub([Candidate(correct, "a.jpg", 0.8, 18, 10), Candidate(other, "b.jpg", 0.2, 5, 1)])
    field = LabelField(2020, "Урожай 2020", (0, 0, 20, 10), 90, "vintage_context")
    with patch("app.service.extract_label", return_value=OcrResult(year=field)):
        result = SearchService(index, catalog=[correct, other]).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["candidates"][0]["slug"] == correct.slug
    assert len(result.body["candidates"]) == 2
    assert result.body["status"] == "uncertain"


def test_timeout_preserves_visual_result_and_diagnostic():
    candidate = Candidate(wine(), "a.jpg", 0.8, 18, 10)
    with patch("app.service.extract_label", return_value=OcrResult(error="timeout")):
        result = SearchService(IndexStub([candidate]), catalog=[wine()]).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "matched"
    assert result.diagnostics["ocr"]["error"] == "timeout"
    assert "diagnostics" not in result.body


def test_close_candidates_are_not_automatic_match():
    first = Candidate(wine(), "a.jpg", 0.8, 18, 10)
    second = replace(first, wine=wine("other", "Другое"), score=0.79)
    with patch("app.service.extract_label", return_value=OcrResult()):
        result = SearchService(IndexStub([first, second]), catalog=[first.wine, second.wine]).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["status"] == "uncertain"


def test_generic_text_does_not_overturn_strong_geometry():
    first = Candidate(wine(), "a.jpg", 0.9, 180, 150)
    second = Candidate(wine("other", "Шардоне", "Агора"), "b.jpg", 0.5, 12, 10)
    with patch("app.service.extract_label", return_value=OcrResult((word("Шардоне Агора"),))):
        result = SearchService(IndexStub([first, second]), catalog=[first.wine, second.wine]).search(np.zeros((10, 10, 3), dtype=np.uint8))
    assert result.body["candidates"][0]["slug"] == first.wine.slug
