from app.catalog import Wine
from app.label_fields import FieldCandidate, RetrievalFields
from app.ranking import RankingResult, rank
from app.recommendations import recommend


MUSKATEL = Wine("muskatel-belyy", "Мускатель белый", "Массандра", category="Белое", grape_varieties=("Мускат Белый",))
MUSKAT = Wine("muskat-yuzhnoberezhnyy", "Мускат Южнобережный", "Массандра", category="Белое",
              grape_varieties=("Мускат Белый",))
PURITY = Wine("purity-in-merlot", "Purity in Merlot", "AYA Organic Wine & Vineyards", category="Розовое",
              grape_varieties=("Мерло",))
STRANGER_RED = Wine("stranger-red", "Кокур 2020", "Табия", category="Красное", sweetness="сухое",
                    grape_varieties=("Кокур",))
STRANGER_MUSKAT = Wine("stranger-muskat", "Солнечная долина", "Солнечная Долина", category="Белое",
                       grape_varieties=("Мускат Белый",))
WINES = {wine.slug: wine for wine in (MUSKATEL, MUSKAT, PURITY, STRANGER_RED, STRANGER_MUSKAT)}


def fields(**values):
    return RetrievalFields(**{field: (FieldCandidate(value, 1.0),) for field, value in values.items()})


def not_found(evidence, rejected=None):
    return RankingResult("not_found", None, max(evidence.values()), 0.0, evidence, rejected or {})


def test_matched_scan_gets_no_recommendations():
    result = RankingResult("matched", MUSKATEL.slug, 0.5, 0.2, {MUSKATEL.slug: 0.5, MUSKAT.slug: 0.1})
    assert recommend(result, fields(winery="Массандра"), WINES) == ()


def test_same_winery_with_a_stated_colour_is_recommended_and_says_so():
    result = not_found({MUSKATEL.slug: 0.3, MUSKAT.slug: 0.2, STRANGER_RED.slug: 0.25})
    recommendations = recommend(result, fields(winery="Массандра", category="Белое"), WINES, ocr_text="МАССАНДРА")
    assert [item.slug for item in recommendations] == [MUSKATEL.slug, MUSKAT.slug]
    assert recommendations[0].shared_fields == ("winery", "category")
    assert "Массандра" in recommendations[0].reason


def test_winery_alone_suggests_nothing():
    # «ФАНАГОРИЯ» on a label the catalog does not know: any of their wines would be a guess.
    result = not_found({MUSKATEL.slug: 0.3, MUSKAT.slug: 0.2})
    assert recommend(result, fields(winery="Массандра"), WINES, ocr_text="МАССАНДРА") == ()


def test_a_winery_named_only_by_common_words_is_no_evidence():
    # OCR takes «Винодельня 78» from «Семейная винодельня Литавщуков».
    wines = [Wine(f"w{i}", f"Сорт{i}", f"Винодельня Хозяйство{i}") for i in range(3)]
    wines.append(Wine("v78", "Саперави", "Винодельня 78", category="Красное"))
    by_slug = {wine.slug: wine for wine in wines}
    result = not_found({"v78": 0.1})
    assert recommend(result, fields(winery="Винодельня 78", category="Красное"), by_slug) == ()


def test_a_word_of_the_wine_name_on_the_label_is_enough_without_the_winery():
    result = not_found({PURITY.slug: 0.1, STRANGER_RED.slug: 0.2})
    recommendations = recommend(result, RetrievalFields(), WINES, ocr_text="PURITY IN BALANCE 2025")
    assert [item.slug for item in recommendations] == [PURITY.slug]
    assert recommendations[0].shared_fields == ("name",)


def test_grape_and_style_without_the_winery_suggest_nothing():
    # «Мускат белое» or «Красное сухое» of an unknown winery is every other wine.
    result = not_found({STRANGER_RED.slug: 0.2, STRANGER_MUSKAT.slug: 0.1})
    assert recommend(result, fields(category="Красное", sweetness="сухое"), WINES, ocr_text="КРАСНОЕ СУХОЕ") == ()
    assert recommend(result, fields(grape_varieties="Мускат Белый", category="Белое"), WINES, ocr_text="МУСКАТ") == ()


def test_winery_with_a_grape_is_related():
    result = not_found({MUSKAT.slug: 0.1})
    recommendations = recommend(result, fields(winery="Массандра", grape_varieties="Мускат Белый"), WINES)
    assert [item.shared_fields for item in recommendations] == [("winery", "grape_varieties")]


def test_grape_words_do_not_count_as_name_words():
    # «Merlot» is the grape of «Purity in Merlot», not its own name.
    result = not_found({PURITY.slug: 0.1})
    assert recommend(result, RetrievalFields(), WINES, ocr_text="MERLOT") == ()


def test_a_wine_the_label_contradicts_stays_and_says_what_differs():
    result = not_found({MUSKATEL.slug: 0.3}, {MUSKATEL.slug: "на этикетке 2023, в каталоге 2021"})
    [recommendation] = recommend(result, fields(winery="Массандра", category="Белое", year="2023"), WINES)
    assert recommendation.difference == "на этикетке 2023, в каталоге 2021"


def test_limit_and_order_follow_ranking_evidence():
    result = not_found({MUSKAT.slug: 0.4, MUSKATEL.slug: 0.3})
    recommendations = recommend(result, fields(winery="Массандра", category="Белое"), WINES, limit=1)
    assert [item.slug for item in recommendations] == [MUSKAT.slug]


def test_recommendations_follow_a_real_ranking_that_did_not_match():
    # A new Massandra wine: the winery is read, no catalog name is.
    ocr_fields = fields(winery="Массандра", category="Белое")
    result = rank(ocr_fields, RetrievalFields(), list(WINES.values()), ocr_text="МАССАНДРА ХЕРЕС")
    assert result.status == "not_found"
    recommendations = recommend(result, ocr_fields, WINES, ocr_text="МАССАНДРА ХЕРЕС")
    assert {item.slug for item in recommendations} == {MUSKATEL.slug, MUSKAT.slug}


def test_a_name_word_many_wineries_use_ties_the_label_to_nothing():
    generic = [Wine("vedernikov", "Винодельня Ведерниковъ Пет-Нат", "Ведерниковъ")] + [
        Wine(f"other-{i}", f"Сорт{i}", f"Винодельня Хозяйство{i}") for i in range(2)]
    wines = {wine.slug: wine for wine in generic}
    result = not_found({wine.slug: 0.1 for wine in generic})
    assert recommend(result, RetrievalFields(), wines, ocr_text="СЕМЕЙНАЯ ВИНОДЕЛЬНЯ") == ()
