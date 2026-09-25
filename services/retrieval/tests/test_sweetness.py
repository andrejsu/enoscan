import pytest

from app.sweetness import catalog_sugar_level, contradicts, sugar_level


@pytest.mark.parametrize("text,level", [
    ("РОЗОВОЕ ПОЛУСУХОЕ 2024", "полусухое"),
    ("Вино розовое сухое", "сухое"),
    ("КРЫМ ЗОЛОТАЯ БАЛКА МУСКАТ ПОЛУСЛАДКОЕ БЕЛОЕ", "полусладкое"),
    ("ARISTOV MILLESIMATO BRUT ROSE 2024", "брют"),
    ("EXTRA BRUT·ZERO DOSAGE", None),  # two different levels on one label: abstain
    ("fanagoriya-extra-brut-rose-2019-igristoe-bryut-rozovoe-ekstra-bryut-12", "экстра брют"),
    ("abrau-dyurso-abrau-kupazh-krasnyy-polsusladkoe-kaberne-sovinon", "полусладкое"),  # catalog typo
    ("Пино Нуар, Мускат п.сл.webp", "полусладкое"),
    ("Пино Нуар, Мускат п.сух.webp", "полусухое"),
    ("Пино Нуар,Мускат сух.webp", "сухое"),
    ("Pino_Nuar_Muskat_p_suh_6f84a398e4.webp", "полусухое"),
    ("Semi-dry rosé", "полусухое"),
    ("Аристов Anima Millesimato", None),
    ("сухое или сладкое", None),
])
def test_one_parser_reads_labels_slugs_and_photo_file_names(text, level):
    assert sugar_level(text) == level


def test_catalog_level_takes_the_first_source_that_names_one():
    # Жемчужная 9 siblings: the level is only in the source photo's file name.
    assert catalog_sugar_level("Жемчужная 9 Пино Нуар, Мускат Розовый", "zhemchuzhnaya-9-pino-nuar-muskat-rozovyj-2",
                               "Пино Нуар, Мускат п.сл.webp") == "полусладкое"
    assert catalog_sugar_level("Полусухое Красное", "perovskih_polusuhoe_krasnoe", "Polusuhoe_beloe.webp") == "полусухое"
    assert catalog_sugar_level("Кокур", "kokur", None) is None


def test_brut_levels_do_not_contradict_each_other():
    assert contradicts("полусухое", "сухое")
    assert not contradicts("брют", "экстра брют")
    assert not contradicts("сухое", "сухое")
