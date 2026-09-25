from unittest.mock import patch

import numpy as np

from app.catalog import Wine
from app.ocr.engine import OcrResult, OcrWord
from app.ocr.retriever import OcrRetriever
from app.ocr.tokens import tokenize
from app.ocr.vocabulary import FieldVocabulary, learn_aliases


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское", **overrides):
    values = dict(slug=slug, name=name, winery=winery,
                  category="Вино", color="Красное", region="Крым", grape_varieties=("Пино Нуар",))
    values.update(overrides)
    return Wine(**values)


def word(text, confidence=90, line=(1, 1, 1)):
    return OcrWord(text, confidence, (0, 0, 80, 20), line)


_DECOY_WINERIES = ("Табия", "Абрау-Дюрсо", "Фанагория", "Массандра", "Инкерман")


def test_field_vocabulary_only_returns_real_catalog_values():
    wines = [wine()] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    vocabulary = FieldVocabulary(wines)
    candidates = vocabulary.top("winery", "Дивноморское")
    assert [c.value for c in candidates] == ["Дивноморское"]


def test_category_vocabulary_accepts_an_exact_single_word_category():
    categories = ("Белое", "Красное", "Розовое", "Оранжевое")
    wines = [wine(f"wine-{index}", f"Вино {index}", category=category)
             for index, category in enumerate(categories)]
    vocabulary = FieldVocabulary(wines)

    for category in categories:
        candidates = vocabulary.top("category", category.upper())

        assert [(candidate.value, candidate.score) for candidate in candidates] == [(category, 1.0)]


def test_foreign_label_word_finds_the_catalog_category():
    categories = ("Белое", "Красное", "Розовое", "Оранжевое")
    wines = [wine(f"wine-{index}", f"Вино {index}", category=category)
             for index, category in enumerate(categories)]
    vocabulary = FieldVocabulary(wines)

    for label, category in [("BRUT ROSE 2024", "Розовое"), ("Rosé", "Розовое"), ("Sauvignon Blanc", "Белое"),
                            ("Rosso Toscana", "Красное"), ("ORANGE", "Оранжевое")]:
        assert [c.value for c in vocabulary.top("category", label)] == [category], label
    assert vocabulary.top("category", "MILLESIMATO BRUT") == ()


def test_one_coincidental_token_does_not_score_full_confidence_on_a_long_name():
    target = wine(name="Millstream Cellar Резерв Бленд Номер Четыре")
    wines = [target] + [wine(f"decoy-{i}", f"Вино Decoy{i} Sort{i}", f"Winery{i}") for i in range(6)]
    candidates = FieldVocabulary(wines).top("name", "случайный мусор бленд ерунда")
    assert candidates
    assert candidates[0].value == target.name
    assert candidates[0].score < 0.5


def test_ocr_retriever_fills_text_fields_but_never_a_slug():
    wines = [wine()] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    retriever = OcrRetriever(FieldVocabulary(wines))
    label = OcrResult((word("Ребус Дивноморское"), word("Урожай 2019", line=(1, 1, 2))))
    with patch("app.ocr.retriever.extract_label", return_value=label):
        trace = retriever.trace(np.zeros((10, 10, 3), dtype=np.uint8))
    assert trace.label is label
    assert trace.fields.winery[0].value == "Дивноморское"
    assert trace.fields.year[0].value == "2019"
    assert trace.fields.slug == ()


def test_label_brand_stem_finds_the_adjectival_catalog_winery():
    wines = [wine(winery="Инкерманский ЗМВ")] + [wine(f"decoy-{name}", f"Вино {name}", name)
                                                  for name in _DECOY_WINERIES if name != "Инкерман"]
    candidates = FieldVocabulary(wines).top("winery", "INKERMAN РОССИЙСК ФЕДЕРАЦ")
    assert candidates and candidates[0].value == "Инкерманский ЗМВ"


def test_short_stems_do_not_prefix_match():
    wines = [wine(winery="Пинотаж Эстейт")] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    assert FieldVocabulary(wines).top("winery", "ПИНО") == ()


def test_french_label_spelling_finds_the_russian_catalog_winery():
    wines = [wine(winery="Шато Пино"), wine("talu", "Chateau de Talu Merlot", "Chateau de Talu")] + \
            [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    candidates = FieldVocabulary(wines).top("winery", "CHATEAU PINOT Беленькое")
    assert candidates[0].value == "Шато Пино"
    assert FieldVocabulary(wines).top("grape_varieties", "Pinot Noir")[0].value == "Пино Нуар"


def test_winery_words_inside_a_name_are_not_name_evidence():
    wines = [wine("aligote", "Aligote. Шато Пино", "Шато Пино"), wine("koldun", "Колдун", "Шато Пино"),
             wine("inkerman", "Инкерман", "Инкерман")] + \
            [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES if name != "Инкерман"]
    vocabulary = FieldVocabulary(wines)
    assert vocabulary.top("name", "CHATEAU PINOT") == ()
    assert vocabulary.top("name", "ALIGOTE")[0].value == "Aligote. Шато Пино"
    assert vocabulary.top("name", "ИНКЕРМАН")[0].value == "Инкерман"


def test_words_spent_on_a_confident_winery_are_not_reused_for_name_or_grape():
    wines = [wine("aligote", "Алиготе - Ркацители", "Шато Пино", grape_varieties=("Алиготе",)),
             wine("noir", "Pinot Noir", "Абрау-Дюрсо", grape_varieties=("Пино Нуар",))] + \
            [wine(f"decoy-{name}", f"Вино {name}", name, grape_varieties=(grape,))
             for name, grape in zip(_DECOY_WINERIES, ("Кокур", "Мерло", "Саперави", "Рислинг", "Шардоне"))]
    retriever = OcrRetriever(FieldVocabulary(wines))
    fields = retriever._fields(OcrResult((word("CHATEAU PINOT"),)))
    assert fields.winery[0].value == "Шато Пино"
    assert fields.name == () and fields.grape_varieties == ()
    fields = retriever._fields(OcrResult((word("CHATEAU PINOT Алиготе"),)))
    assert fields.grape_varieties[0].value == "Алиготе"


def test_label_and_catalog_spellings_share_one_token():
    for label, catalog in [("CHATEAU", "Шато"), ("PINOT", "Пино"), ("Noir", "Нуар"), ("Merlot", "Мерло"),
                           ("Cabernet", "Каберне"), ("Sauvignon", "Совиньон"), ("Chardonnay", "Шардоне"),
                           ("Blanc", "Блан"), ("Riesling", "Рислинг"), ("Château", "Шато"), ("KRYM", "Крым")]:
        assert tokenize(label) == tokenize(catalog), (label, catalog)


def test_catalog_teaches_pairs_the_sound_rules_miss():
    wines = [wine(f"k{i}", f"Kodzor Wine {i}", "Кодзора") for i in range(3)] + \
            [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    assert learn_aliases(wines)["kodzor"] == "kodzora"
    assert FieldVocabulary(wines).top("winery", "KODZOR")[0].value == "Кодзора"


def test_one_coincidence_is_not_an_alias():
    wines = [wine("a", "Kodzor", "Кодзора")] + [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    assert "kodzor" not in learn_aliases(wines)


def test_ocr_reads_the_middle_of_a_photo_and_falls_back_to_the_full_frame():
    retriever = OcrRetriever(FieldVocabulary([wine()]))
    photo = np.zeros((4000, 3000, 3), dtype=np.uint8)
    readable = OcrResult((word("Ребус"), word("Дивноморское", line=(1, 1, 2)), word("2019", line=(1, 1, 3))))
    with patch("app.ocr.retriever.extract_label", return_value=readable) as extract:
        assert retriever.trace(photo).passes == ("crop",)
    assert extract.call_args.args[0].shape == (3000, 1500, 3)  # OCR_CROP_BOX of a 3000×4000 photo

    with patch("app.ocr.retriever.extract_label", side_effect=[OcrResult(), readable]) as extract:
        trace = retriever.trace(photo)
    assert trace.passes == ("crop", "full") and extract.call_args.args[0].shape == (4000, 3000, 3)

    bottle = np.zeros((6000, 1400, 3), dtype=np.uint8)  # a tall bottle shot: keep its full width
    with patch("app.ocr.retriever.extract_label", return_value=readable) as extract:
        retriever.trace(bottle)
    assert extract.call_args.args[0].shape == (4500, 1400, 3)

    close_up = np.zeros((447, 447, 3), dtype=np.uint8)  # already a close-up: read whole, once
    with patch("app.ocr.retriever.extract_label", return_value=readable) as extract:
        assert retriever.trace(close_up).passes == ("full",)
    assert extract.call_args.args[0].shape == (447, 447, 3)


def test_a_grape_word_alone_never_names_a_winery():
    # Regression (Жемчужная 9 «ПИНО НУАР»): «Пино» matched the winery «Шато Пино».
    wines = [wine(winery="Шато Пино", grape_varieties=("Пино Нуар",)),
             wine("zh", "Жемчужная 9 Пино Нуар", "АРАТТИ", grape_varieties=("Пино Нуар",))] + \
            [wine(f"decoy-{name}", f"Вино {name}", name) for name in _DECOY_WINERIES]
    vocabulary = FieldVocabulary(wines)
    assert vocabulary.top("winery", "ЖЕМЧУЖНАЯ ПИНО НУАР РОЗОВОЕ") == ()
    assert vocabulary.top("winery", "CHATEAU PINOT")[0].value == "Шато Пино"
