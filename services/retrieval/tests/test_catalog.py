import unittest

from app.catalog import Wine
from app.index import Candidate
from app.ocr import extract_year, text_score
from app.service import year_adjustment


def wine(**overrides: object) -> Wine:
    values: dict[str, object] = {
        "slug": "pino-nuar-2025",
        "name": "Пино Нуар, 2025",
        "winery": "Табия",
        "category": "Вино",
        "color": "Красное",
        "region": "Крым",
        "grape_varieties": ("Пино Нуар",),
        "description": "Описание",
    }
    values.update(overrides)
    return Wine(**values)


class CatalogTest(unittest.TestCase):
    def test_wine_card_extracts_year_and_grapes(self) -> None:
        card = wine(grape_varieties=("Пино Нуар", "Мерло")).as_card()

        self.assertEqual(card["year"], 2025)
        self.assertEqual(card["category"], "Вино")
        self.assertEqual(card["color"], "Красное")
        self.assertEqual(card["grapeVarieties"], ["Пино Нуар", "Мерло"])

    def test_ocr_text_breaks_duplicate_image_tie(self) -> None:
        pinot = wine()
        kokur = wine(slug="method-classic-kokur", name="Method Classic Кокур")
        label = "ТАБИЯ Пино Нуар полусухое 2025"

        self.assertGreater(text_score(label, pinot), text_score(label, kokur))

    def test_wine_card_image_urls_follow_mapping(self) -> None:
        with_image = wine(slug="pino nuar", has_image=True).as_card()
        without_image = wine().as_card()

        self.assertEqual(with_image["imageUrl"], "/api/wines/pino%20nuar/image")
        self.assertEqual(with_image["imagePreviewUrl"], "/api/wines/pino%20nuar/image?size=preview")
        self.assertIsNone(without_image["imageUrl"])
        self.assertIsNone(without_image["imagePreviewUrl"])

    def test_wine_json_round_trip_keeps_grapes_as_tuple(self) -> None:
        item = wine(grape_varieties=("Кокур", "Мускат"), has_image=True)

        self.assertEqual(Wine.from_json(item.to_json()), item)


def candidate(slug: str, name: str, score: float = 0.5) -> Candidate:
    return Candidate(
        wine=wine(slug=slug, name=name),
        image_sha256=f"{slug}-sha",
        score=score,
        good_matches=12,
        inliers=8,
    )


class OcrYearTest(unittest.TestCase):
    def test_extracts_single_year(self) -> None:
        self.assertEqual(extract_year("Урожай 2019 года"), 2019)

    def test_repeated_same_year_is_not_ambiguous(self) -> None:
        self.assertEqual(extract_year("2019 Ребус 2019"), 2019)

    def test_conflicting_years_are_ambiguous(self) -> None:
        self.assertIsNone(extract_year("2019 или 2020 неизвестно"))

    def test_absent_year_returns_none(self) -> None:
        self.assertIsNone(extract_year("красное вино"))

    def test_year_outside_vintage_range_is_ignored(self) -> None:
        self.assertIsNone(extract_year("основано в 1861"))


class YearEvidenceTest(unittest.TestCase):
    def test_year_is_soft_evidence(self):
        self.assertGreater(year_adjustment(wine(name="Ребус 2019"), 2019), 0)
        self.assertLess(year_adjustment(wine(name="Ребус 2020"), 2019), 0)

    def test_missing_or_ambiguous_year_is_neutral(self):
        self.assertEqual(year_adjustment(wine(name="Ребус"), 2019), 0)
        self.assertEqual(year_adjustment(wine(name="Ребус 2019"), None), 0)
        self.assertEqual(year_adjustment(wine(name="Ребус 2019 2020"), 2019), 0)


if __name__ == "__main__":
    unittest.main()
