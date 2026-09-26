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
    leader, other = wine("petnat-riesling", "Петнат Рислинг"), wine("petnat-rubin", "Пет-Нат Рубин")
    ocr_fields = RetrievalFields(name=(FieldCandidate("Пет-Нат Рубин", 0.50),),
                                 winery=(FieldCandidate("Дивноморское", 1.0),))
    result = rank(ocr_fields, visual(("petnat-riesling", 0.78), ("petnat-rubin", 0.52)), [leader, other])
    assert result.ranked(1)[0][0] == "petnat-riesling"


def test_field_that_cannot_tell_candidates_apart_does_not_reorder_them():
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
    assert breakdown["name"].score == pytest.approx(1.0)
    assert breakdown["winery"].score == 0.0
    expected = sum(item.weight * item.score for item in breakdown.values()) / TOTAL_WEIGHT
    result = rank(ocr_fields, visual_fields, [target])
    assert result.score == pytest.approx(expected, abs=1e-4)


def test_shared_field_alone_never_matches():
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


ANIMA = [wine("blush", "Аристов Anima Pinot Grigio Blush", "Кубань-Вино", category="Розовое"),
         wine("brut-white", "Аристов ANIMA Millesimato белое брют", "Кубань-Вино", category="Белое"),
         wine("millesimato", "Аристов Anima Millesimato", "Кубань-Вино", category="Розовое"),
         wine("roze", "Аристов 8 Розе", "Кубань-Вино", category="Розовое")]
ANIMA_VISUAL = visual(("blush", 0.679), ("brut-white", 0.639), ("millesimato", 0.628))


def test_label_word_of_a_sibling_overturns_the_visual_leader():
    ocr_fields = RetrievalFields(name=(FieldCandidate("Аристов 8 Розе", 0.33),
                                       FieldCandidate("Аристов Anima Millesimato", 0.29),
                                       FieldCandidate("Аристов ANIMA Millesimato белое брют", 0.24)),
                                 category=(FieldCandidate("Розовое", 1.0),))
    result = rank(ocr_fields, ANIMA_VISUAL, ANIMA, ocr_text="ARISTOV ANMA MILLESIMATO BRUT ROSE 2024")
    assert result.rejected.keys() == {"blush", "brut-white", "roze"}
    kinds = {check.slug: check.kind for check in result.checks}
    assert kinds == {"blush": "name", "brut-white": "category", "millesimato": None, "roze": "name"}
    assert "«Millesimato»" in result.rejected["blush"]
    assert next(c for c in result.checks if c.slug == "millesimato").read_words == ("Аристов", "Millesimato")
    assert result.status == "matched" and result.slug == "millesimato"
    assert [slug for slug, _ in result.ranked(4)][0] == "millesimato"


def test_without_label_text_the_shortlist_is_not_checked():
    result = rank(RetrievalFields(), ANIMA_VISUAL, ANIMA)
    assert result.rejected == {}
    assert result.ranked(1)[0][0] == "blush"


def test_a_word_every_sibling_shares_rejects_nobody():
    wines = [wine("petnat-riesling", "Петнат Рислинг"), wine("petnat-rubin", "Пет-Нат Рубин")]
    ocr_fields = RetrievalFields(name=(FieldCandidate("Пет-Нат Рубин", 0.50),))
    result = rank(ocr_fields, visual(("petnat-riesling", 0.78), ("petnat-rubin", 0.52)), wines, ocr_text="Пет-Нат")
    assert result.rejected == {}
    assert result.ranked(1)[0][0] == "petnat-riesling"


def test_a_different_vintage_on_the_label_rejects_the_catalog_vintage():
    wines = [wine("avrora-2023", "Аврора 2023"), wine("avrora-2024", "Аврора 2024")]
    ocr_fields = RetrievalFields(year=(FieldCandidate("2024", 0.99),))
    result = rank(ocr_fields, visual(("avrora-2023", 0.70), ("avrora-2024", 0.60)), wines, ocr_text="АВРОРА 2024")
    assert result.rejected.keys() == {"avrora-2023"}
    assert result.status == "matched" and result.slug == "avrora-2024"


def test_label_that_contradicts_every_close_wine_is_not_found():
    wines = [wine("a", "Кокур", category="Белое"), wine("b", "Мерло", category="Белое")]
    ocr_fields = RetrievalFields(category=(FieldCandidate("Красное", 1.0),))
    result = rank(ocr_fields, visual(("a", 0.9), ("b", 0.5)), wines, ocr_text="Rosso")
    assert result.rejected.keys() == {"a", "b"}
    assert result.status == "not_found"


def test_label_year_confirms_a_found_wine_but_finds_none_alone():
    target, dated = wine("cuvee", "Кюве Александр", "Аристов"), wine("david", "Давид 2022", "Другая")
    ocr_fields = RetrievalFields(year=(FieldCandidate("2022", 0.99),))
    result = rank(ocr_fields, visual(("cuvee", 0.6)), [target, dated])
    assert result.evidence["david"] == 0.0
    assert rank(ocr_fields, visual(("david", 0.6)), [target, dated]).evidence["david"] == \
        rank(RetrievalFields(), visual(("david", 0.6)), [target, dated]).evidence["david"]
    confirmed = wine("cuvee-2022", "Кюве Александр 2022", "Аристов")
    named = RetrievalFields(name=(FieldCandidate(confirmed.name, 0.5),), year=ocr_fields.year)
    assert rank(named, visual(("cuvee-2022", 0.6)), [confirmed]).evidence["cuvee-2022"] > \
        rank(RetrievalFields(name=named.name), visual(("cuvee-2022", 0.6)), [confirmed]).evidence["cuvee-2022"]


def test_the_name_ocr_read_is_checked_even_outside_the_visual_top():
    wines = [wine("kagor", "Кагор Гурзуф", "Массандра"), wine("portvein", "Портвейн Белый Гурзуф", "Массандра"),
             wine("muskat", "Мускат Белый Южнобережный", "Массандра"), wine("muskatel", "Мускатель белый", "Массандра")]
    ocr_fields = RetrievalFields(name=(FieldCandidate("Мускатель белый", 0.6),),
                                 winery=(FieldCandidate("Массандра", 0.9),))
    result = rank(ocr_fields, visual(("kagor", 0.72), ("portvein", 0.70), ("muskat", 0.69)), wines,
                  ocr_text="МАССАНДРА МУСКАТЕЛЬ БЕЛЫЙ ГОД УРОЖАЯ 2023")
    assert result.rejected.keys() == {"kagor", "portvein", "muskat"}
    assert result.status == "matched" and result.slug == "muskatel"


def test_ocr_alone_needs_the_distinctive_words_of_the_name_on_the_label():
    generic, named = wine("novyy-svet", "Пино Нуар полусухое", "Новый Свет"), wine("muskatel", "Мускатель белый")
    ocr_fields = RetrievalFields(name=(FieldCandidate(generic.name, 0.63),))
    result = rank(ocr_fields, RetrievalFields(), [generic, named], ocr_text="ТАБИЯ ВИНОДЕЛЬНЯ Пино Нуар полусухое 2025")
    assert result.ranked(1)[0][0] == "novyy-svet" and result.status == "not_found"
    ocr_fields = RetrievalFields(name=(FieldCandidate(named.name, 0.6),))
    assert rank(ocr_fields, RetrievalFields(), [generic, named], ocr_text="МУСКАТЕЛЬ БЕЛЫЙ").slug == "muskatel"


def test_label_sugar_level_picks_the_one_of_identical_siblings():
    name = "Жемчужная 9 Пино Нуар, Мускат Розовый"
    siblings = [wine(slug, name, "Жемчужная", category="Розовое", sweetness=level)
                for slug, level in (("dry", "сухое"), ("semi-dry", "полусухое"), ("semi-sweet", "полусладкое"))]
    others = [wine(f"decoy-{i}", f"Вино {i}", "Другая") for i in range(3)]
    ocr_fields = RetrievalFields(name=(FieldCandidate(name, 0.8),), sweetness=(FieldCandidate("полусухое", 1.0),))
    result = rank(ocr_fields, visual(("semi-sweet", 0.71), ("dry", 0.70), ("semi-dry", 0.69)), siblings + others,
                  ocr_text="ЖЕМЧУЖНАЯ 9 ПИНО НУАР МУСКАТ РОЗОВЫЙ РОЗОВОЕ ПОЛУСУХОЕ 2024")
    kinds = {check.slug: check.kind for check in result.checks}
    assert (kinds["dry"], kinds["semi-dry"], kinds["semi-sweet"]) == ("sweetness", None, "sweetness")
    assert result.status == "matched" and result.slug == "semi-dry"


def test_a_faint_visual_share_plus_shared_fields_does_not_identify_a_wine():
    # A new Inkerman «Каберне»: its label design is the family's, so the
    # visual share spreads over the whole range, and winery, grape and colour
    # fit the one Cabernet red of the catalog — without its name on the label.
    target = wine("shato-ruzh", "Inkerman Шато Руж", "Инкерманский ЗМВ", category="Красное",
                  grape_varieties=("Каберне Совиньон",))
    family = [wine(f"sibling-{i}", f"Инкерман Сорт{i}", "Инкерманский ЗМВ", category="Красное",
                   grape_varieties=("Саперави",)) for i in range(7)]
    ocr_fields = RetrievalFields(winery=(FieldCandidate("Инкерманский ЗМВ", 1.0),),
                                 grape_varieties=(FieldCandidate("Каберне Совиньон", 1.0),),
                                 category=(FieldCandidate("Красное", 1.0),))
    visual_fields = visual(*((item.slug, 0.46) for item in [target, *family]))
    result = rank(ocr_fields, visual_fields, [target, *family], ocr_text="INKERMAN КАБЕРНЕ СУХОЕ КРАСНОЕ")
    assert result.ranked(1)[0][0] == target.slug
    assert result.status == "not_found"


TABIYA_OCR = RetrievalFields(winery=(FieldCandidate("Табия", 0.39), FieldCandidate("Винодельня 78", 0.23)),
                             sweetness=(FieldCandidate("полусухое", 1.0),))


def test_a_winery_on_the_label_rejects_a_wine_of_another_winery():
    # «ТАБИЯ ВИНОДЕЛЬНЯ Пино Нуар полусухое»: not Новый Свет's Pinot Noir, however alike the bottles.
    novyy_svet = wine("ns-pinot", "Пино Нуар полусухое", "Новый Свет. Дом шампанских вин")
    tabiya = wine("bukovinka", "Буковинка", "Табия")
    result = rank(TABIYA_OCR, visual(("ns-pinot", 0.9), ("bukovinka", 0.5)), [novyy_svet, tabiya],
                  ocr_text="ТАБИЯ ВИНОДЕЛЬНЯ Пино Нуар полусухое 2025")
    assert result.rejected.keys() == {"ns-pinot"}
    assert result.slug != "ns-pinot"


def test_the_wine_own_name_or_winery_on_the_label_keeps_it_despite_another_winery_read():
    # OCR's winery field may pick a neighbour's winery; the wine's own words on the label still speak for it.
    anima = wine("anima", "Аристов Anima Millesimato", "Кубань-Вино")
    ocr_fields = RetrievalFields(winery=(FieldCandidate("Табия", 0.4),))
    result = rank(ocr_fields, visual(("anima", 0.9)), [anima, wine("bukovinka", "Буковинка", "Табия")],
                  ocr_text="ТАБИЯ ANIMA MILLESIMATO")
    assert "anima" not in result.rejected


def test_a_winery_word_many_wineries_share_contradicts_nobody():
    wines = [wine(f"w{i}", f"Сорт{i}", f"Винодельня Хозяйство{i}") for i in range(3)]
    ocr_fields = RetrievalFields(winery=(FieldCandidate("Винодельня Хозяйство0", 0.3),))
    result = rank(ocr_fields, visual(("w1", 0.9)), wines, ocr_text="СЕМЕЙНАЯ ВИНОДЕЛЬНЯ")
    assert result.rejected == {}
