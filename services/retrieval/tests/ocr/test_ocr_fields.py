import pytest

from app.ocr.engine import OcrWord
from app.ocr.fields import extract_abv_candidates, extract_year, extract_year_candidates


def word(text, confidence=90, line=(1, 1, 1)):
    return OcrWord(text, confidence, (0, 0, 80, 20), line)


@pytest.mark.parametrize("text,expected", [
    ("Урожай 2019 года", 2019),
    ("2019 Ребус 2019", 2019),
    ("2019 или 2020 неизвестно", None),
    ("красное вино", None),
    ("основано в 1861", None),
])
def test_extract_year_needs_one_unambiguous_vintage(text, expected):
    assert extract_year(text) == expected


@pytest.mark.parametrize("text,years,abvs", [
    ("Урожай 2019 12,5 %", ["2019"], ["12.5"]),
    ("Основано в 2019", [], []),
    ("0,75 л", [], []),
    ("alc 13.5", [], ["13.5"]),
    ("2019 розлив урожай", [], []),
])
def test_fields_need_context(text, years, abvs):
    assert [c.value for c in extract_year_candidates([word(text)])] == years
    assert [c.value for c in extract_abv_candidates([word(text)])] == abvs


@pytest.mark.parametrize("lines,years", [
    (["MILLESIMATO", "BRUT ROSE 2024"], ["2024"]),
    (["2019"], ["2019"]),
    (["Урожай 2019", "Cuvee 2021"], ["2019"]),
    (["2019", "2021"], []),
    (["Since 1995", "Brut"], []),
    (["Годен до 15.03.2024"], []),
    (["ГОСТ 32030-2013"], []),
    (["ГОСТ Р 55242 2012"], []),
])
def test_label_without_a_harvest_word_yields_its_only_year(lines, years):
    words = [word(text, line=(1, 1, index)) for index, text in enumerate(lines)]
    assert [c.value for c in extract_year_candidates(words)] == years


def test_low_confidence_year_abstains():
    assert extract_year_candidates([word("Урожай 2019", confidence=25)]) == ()


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
