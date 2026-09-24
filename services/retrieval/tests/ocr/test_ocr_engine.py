from unittest.mock import patch

import numpy as np
import pytest

from app.ocr.engine import OcrWord, extract_label, fold_homoglyphs


@pytest.mark.parametrize("text,expected", [
    ("KPACHOE", "KPACHOE КРАСНОЕ"),
    ("ДЕHИCOB", "ДЕНИСОВ"),
    ("3АKAT", "ЗАКАТ"),
    ("3AKAT", "3AKAT ЗАКАТ"),
    ("KOKUR", "KOKUR"),
    ("Урожай 2023г", "Урожай 2023г"),
    ("Merlot", "Merlot"),
])
def test_homoglyphs_fold_to_cyrillic(text, expected):
    assert fold_homoglyphs(text) == expected


class EngineResult:
    boxes = [[[10, 20], [110, 22], [110, 60], [10, 58]]]
    txts = ("Усадьба Перавских KPACHOE",)
    scores = (0.93,)


def test_engine_lines_become_words_with_bbox_and_percent_confidence():
    with patch("app.ocr.engine.load_engine", return_value=lambda image: EngineResult()):
        result = extract_label(np.zeros((100, 200, 3), dtype=np.uint8))
    assert result.words == (OcrWord("Усадьба Перавских KPACHOE КРАСНОЕ", 93.0, (10, 20, 100, 40), (1, 1, 1)),)


def test_no_text_found_is_an_empty_result():
    empty = type("Empty", (), {"boxes": None, "txts": None, "scores": None})()
    with patch("app.ocr.engine.load_engine", return_value=lambda image: empty):
        assert extract_label(np.zeros((10, 10, 3), dtype=np.uint8)).words == ()
