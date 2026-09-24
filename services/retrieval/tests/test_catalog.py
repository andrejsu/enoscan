import unittest

from app.catalog import Wine
from app.index import Candidate


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


if __name__ == "__main__":
    unittest.main()
