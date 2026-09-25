import pytest

from app.catalog import Wine
from app.label_fields import FieldCandidate, RetrievalFields
from app.ranking import MIN_MARGIN, TOTAL_WEIGHT, field_breakdown, field_distribution, rank


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское", **overrides):
    values = dict(slug=slug, name=name, winery=winery,
                  category="Вино", color="Красное", region="Крым", grape_varieties=("Пино Нуар",))
    values.update(overrides)
    return Wine(**values)


def visual(*pairs):
    return RetrievalFields(slug=tuple(FieldCandidate(slug, score) for slug, score in pairs))


def test_required_fields_alone_can_match():
    target = wine()
    other = wine("other", "Кокур 2020", "Табия")
    ocr_fields = RetrievalFields(
        name=(FieldCandidate(target.name, 1.0),),
        winery=(FieldCandidate(target.winery, 1.0),),
    )
    result = rank(ocr_fields, RetrievalFields(), [target, other])
    assert result.status == "matched"
    assert result.slug == target.slug
    assert result.margin >= MIN_MARGIN


def test_every_block_only_adds_support():
    # Blocks help each other: agreeing evidence raises a wine's score, and a
    # block with no opinion about it (another winery read) never lowers it.
    target, other = wine(), wine("other", "Кокур 2020", "Табия")
    visual_only = RetrievalFields(), visual((target.slug, 0.9), ("other", 0.7))
    with_name = RetrievalFields(name=(FieldCandidate(target.name, 0.5),)), visual_only[1]
    with_foreign_winery = RetrievalFields(name=(FieldCandidate(target.name, 0.5),),
                                          winery=(FieldCandidate("Табия", 1.0),)), visual_only[1]
    scores = [rank(*inputs, [target, other]).evidence[target.slug]
              for inputs in (visual_only, with_name, with_foreign_winery)]
    assert scores[0] < scores[1] == scores[2]


def test_visual_only_evidence_can_match_without_any_ocr_text():
    target = wine()
    result = rank(RetrievalFields(), visual((target.slug, 0.9)), [target, wine("other", "Кокур")])
    assert result.status == "matched"
    assert result.slug == target.slug


def test_correct_top1_matches_even_when_raw_ocr_scores_are_low():
    # Regression (yaiyla-kokur photo): OCR noise kept the right wine's raw name
    # score at 0.28 and winery at 0.41, so the old absolute 0.45 threshold
    # rejected a top-1 that led by 0.1. Only the lead should matter.
    target, sibling = wine("kokur", "Кокур", "Яйла"), wine("kokur-rose", "Кокур розовый", "Яйла")
    ocr_fields = RetrievalFields(
        name=(FieldCandidate("Кокур", 0.28), FieldCandidate("Кокур розовый", 0.12)),
        winery=(FieldCandidate("Яйла", 0.41),),
    )
    result = rank(ocr_fields, visual(("kokur", 0.66), ("kokur-rose", 0.61)), [target, sibling])
    assert result.status == "matched" and result.slug == "kokur"


def test_near_tied_top_two_is_an_honest_not_found():
    wines = [wine("a", "Кокур"), wine("b", "Мерло")]
    result = rank(RetrievalFields(), visual(("a", 0.80), ("b", 0.795)), wines)
    assert result.status == "not_found"
    assert result.slug is None
    assert 0 < result.margin < MIN_MARGIN


def test_ocr_name_miss_does_not_overturn_a_clear_visual_leader():
    # Regression (denisov petnat): OCR read «Пет-Нат», so only another Pet-Nat
    # was among the name candidates. The old average zeroed the leader's name
    # term and picked visual #4.
    leader, other = wine("petnat-riesling", "Петнат Рислинг"), wine("petnat-rubin", "Пет-Нат Рубин")
    ocr_fields = RetrievalFields(name=(FieldCandidate("Пет-Нат Рубин", 0.50),),
                                 winery=(FieldCandidate("Дивноморское", 1.0),))
    result = rank(ocr_fields, visual(("petnat-riesling", 0.78), ("petnat-rubin", 0.52)), [leader, other])
    assert result.ranked(1)[0][0] == "petnat-riesling"


def test_field_that_cannot_tell_candidates_apart_does_not_reorder_them():
    # Regression (cantiani-brut): OCR read only «Cantiani»; four names within
    # 0.04 of each other used to outvote the visual top-1.
    names = {"brut": "Cantiani Brut", "riesling": "Cantiani Riesling", "merlot": "Cantiani Merlot"}
    wines = [wine(slug, name) for slug, name in names.items()]
    ocr_fields = RetrievalFields(name=(FieldCandidate("Cantiani Riesling", 0.598),
                                       FieldCandidate("Cantiani Merlot", 0.589),
                                       FieldCandidate("Cantiani Brut", 0.560)))
    result = rank(ocr_fields, visual(("brut", 0.734), ("riesling", 0.719), ("merlot", 0.68)), wines)
    assert result.ranked(1)[0][0] == "brut"


def test_low_ranked_candidates_get_almost_no_credit():
    distribution = field_distribution((FieldCandidate("a", 0.9), FieldCandidate("b", 0.5)), 0.1)
    assert distribution["a"] > 0.98
    assert sum(distribution.values()) == pytest.approx(1.0)


def test_no_catalog_wines_is_not_found():
    result = rank(RetrievalFields(), RetrievalFields(), [])
    assert result.status == "not_found"
    assert result.slug is None


def test_no_evidence_at_all_is_not_found():
    result = rank(RetrievalFields(), RetrievalFields(), [wine()])
    assert result.status == "not_found" and result.score == 0.0


def test_field_breakdown_explains_the_score_and_skips_fields_without_evidence():
    target = wine()
    ocr_fields = RetrievalFields(
        name=(FieldCandidate(target.name, 0.8),),
        winery=(FieldCandidate("Табия", 1.0),),
    )
    visual_fields = visual((target.slug, 0.6))
    breakdown = {item.field: item for item in field_breakdown(target, ocr_fields, visual_fields)}
    assert set(breakdown) == {"name", "winery", "slug"}
    assert breakdown["name"].score == pytest.approx(1.0)  # the field's only candidate
    assert breakdown["winery"].score == 0.0  # evidence exists, but for another winery
    expected = sum(item.weight * item.score for item in breakdown.values()) / TOTAL_WEIGHT
    result = rank(ocr_fields, visual_fields, [target])
    assert result.score == pytest.approx(expected, abs=1e-4)


def test_shared_field_alone_never_matches():
    # Regression: OCR reading only "Красное" scored every red wine 1.0 and
    # "matched" whichever came first in catalog order.
    wines = [wine("a", "Кокур 2020"), wine("b", "Мерло 2021", category="Игристое")]
    result = rank(RetrievalFields(category=(FieldCandidate("Вино", 1.0),)), RetrievalFields(), wines)
    assert result.ranked(1)[0][0] == "a" and result.margin > 0
    assert result.status == "not_found"


def test_winery_with_several_wines_does_not_match_without_a_name():
    wines = [wine("a", "Кокур 2020"), wine("b", "Мерло 2021", region="Кубань")]
    ocr_fields = RetrievalFields(winery=(FieldCandidate("Дивноморское", 1.0),),
                                 region=(FieldCandidate("Крым", 1.0),))
    assert rank(ocr_fields, RetrievalFields(), wines).status == "not_found"


def test_tied_top_candidates_do_not_match():
    wines = [wine("a", "Ребус"), wine("b", "Ребус")]
    ocr_fields = RetrievalFields(name=(FieldCandidate("Ребус", 1.0),))
    result = rank(ocr_fields, RetrievalFields(), wines)
    assert result.status == "not_found" and result.margin == 0.0
