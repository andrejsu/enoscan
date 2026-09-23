from unittest.mock import patch

import numpy as np

from app.catalog import Wine
from app.field_vocabulary import FieldVocabulary
from app.label_normalize import PreparedQuery
from app.ocr import OcrResult, OcrWord, extract_abv_candidates, extract_year_candidates
from app.ocr_retriever import OcrRetriever


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское", **overrides):
    values = dict(slug=slug, name=name, winery=winery,
                  category="Вино", color="Красное", region="Крым", grape_varieties=("Пино Нуар",))
    values.update(overrides)
    return Wine(**values)


def word(text, confidence=90, line=(1, 1, 1)):
    return OcrWord(text, confidence, (0, 0, 80, 20), line)


def test_year_candidates_keep_multiple_readings_instead_of_abstaining():
    words = [word("Урожай 2019"), word("Урожай 2020", line=(1, 1, 2))]
    candidates = extract_year_candidates(words)
    assert {c.value for c in candidates} == {"2019", "2020"}
    assert all(0 < c.score <= 1 for c in candidates)


def test_year_candidates_capped_at_ten_and_sorted_descending():
    words = [word(f"Урожай {year}", confidence=90 - (year % 15), line=(1, 1, year)) for year in range(2000, 2020)]
    candidates = extract_year_candidates(words)
    assert len(candidates) <= 10
    assert list(candidates) == sorted(candidates, key=lambda c: c.score, reverse=True)


def test_abv_candidates_collect_every_reading():
    words = [word("12,5 %"), word("13 %", line=(1, 1, 2))]
    candidates = extract_abv_candidates(words)
    assert {c.value for c in candidates} == {"12.5", "13.0"}


# A single-winery catalog can never clear FieldSearch's "one uncommon token"
# guard (same guard as text_search.TextSearch — see field_vocabulary.py):
# with too few documents, no token's IDF weight reaches the >=2 bar. A
# handful of distinct decoy wineries gets the fixture catalog to a
# realistic-enough size for that guard to behave as it does in production.
_DECOY_WINERIES = ("Табия", "Абрау-Дюрсо", "Фанагория", "Массандра", "Инкерман")


def test_field_vocabulary_only_returns_real_catalog_values():
    wines = [wine()] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    vocabulary = FieldVocabulary(wines)
    candidates = vocabulary.top("winery", "Дивноморское")
    assert [c.value for c in candidates] == ["Дивноморское"]


def test_one_coincidental_token_does_not_score_full_confidence_on_a_long_name():
    # Regression: garbled OCR on an unrelated photo shared exactly one rare
    # token ("бленд") with "MILLSTREAM Cellar Резерв Бленд №4" and used to
    # score a full 1.0 — normalizing only against the (tiny) pool of matched
    # evidence, never against how much of the candidate's OWN identity that
    # evidence actually covered.
    target = wine(name="Millstream Cellar Резерв Бленд Номер Четыре")
    wines = [target] + [wine(f"decoy-{i}", f"Вино Decoy{i} Sort{i}", f"Winery{i}") for i in range(6)]
    candidates = FieldVocabulary(wines).top("name", "случайный мусор бленд ерунда")
    assert candidates
    assert candidates[0].value == target.name
    assert candidates[0].score < 0.5


def test_ocr_retriever_fills_text_fields_but_never_a_slug():
    wines = [wine()] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    retriever = OcrRetriever(FieldVocabulary(wines))
    prepared = PreparedQuery(visual=np.zeros((10, 10, 3), dtype=np.uint8),
                             ocr=np.zeros((10, 10, 3), dtype=np.uint8), used_sam=False)
    label = OcrResult((word("Ребус Дивноморское"), word("Урожай 2019", line=(1, 1, 2))))
    with patch("app.ocr_retriever.prepare_query", return_value=prepared), \
         patch("app.ocr_retriever.extract_label", return_value=label):
        fields = retriever.extract(np.zeros((10, 10, 3), dtype=np.uint8))
    assert fields.winery[0].value == "Дивноморское"
    assert fields.year[0].value == "2019"
    assert fields.slug == ()  # OCR never resolves a wine/slug itself — that's ranking's job
