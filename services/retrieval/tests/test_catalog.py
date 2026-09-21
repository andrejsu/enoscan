import unittest

from app.catalog import Media, Wine, media_stem, normalize_key, resolve_references
from app.catalog_browser import catalog_record
from app.index import IndexedReference
from app.index import Candidate
from app.ocr import extract_year, text_score
from app.service import year_adjustment


def wine(**overrides: str) -> Wine:
    values = {
        "slug": "pino-nuar-2025",
        "name": "Пино Нуар, 2025",
        "winery": "Табия",
        "category": "Вино",
        "color": "Красное",
        "region": "Крым",
        "grape_varieties": "Пино Нуар",
        "description": "Описание",
        "image_filename": "DSC00836.webp",
    }
    values.update(overrides)
    return Wine(**values)


class CatalogTest(unittest.TestCase):
    def test_media_stem_removes_strapi_hash(self) -> None:
        self.assertEqual(media_stem("DSC_00836_4070f8fd2f.webp"), "DSC_00836")

    def test_normalize_key_ignores_filename_separators(self) -> None:
        self.assertEqual(normalize_key("DSC_00836"), normalize_key("dsc00836"))

    def test_resolver_prefers_original_image_filename(self) -> None:
        media = [
            Media("thumbnail_DSC_00836_4070f8fd2f.webp", "thumbnail.webp", 10),
            Media("DSC_00836_4070f8fd2f.webp", "original.webp", 100),
        ]

        references = resolve_references([wine()], media)

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].relative_path, "original.webp")
        self.assertEqual(references[0].mapping_kind, "image_filename")

    def test_wine_card_extracts_year_and_grapes(self) -> None:
        card = wine(grape_varieties="Пино Нуар, Мерло").as_card()

        self.assertEqual(card["year"], 2025)
        self.assertEqual(card["category"], "Вино")
        self.assertEqual(card["color"], "Красное")
        self.assertEqual(card["grapeVarieties"], ["Пино Нуар", "Мерло"])

    def test_ocr_text_breaks_duplicate_image_tie(self) -> None:
        pinot = wine()
        kokur = wine(slug="method-classic-kokur", name="Method Classic Кокур")
        label = "ТАБИЯ Пино Нуар полусухое 2025"

        self.assertGreater(text_score(label, pinot), text_score(label, kokur))

    def test_catalog_record_exposes_image_mapping_diagnostics(self) -> None:
        item = wine()
        reference = IndexedReference(
            wine=item,
            relative_path="pino.webp",
            mapping_kind="image_filename",
            mapping_score=1.0,
        )

        record = catalog_record(item, reference, raw_record_count=2)

        self.assertEqual(record["imageUrl"], "/api/wines/pino-nuar-2025/image")
        self.assertEqual(record["referencePath"], "pino.webp")
        self.assertEqual(record["rawRecordCount"], 2)
        self.assertTrue(record["isIndexed"])



def candidate(slug: str, name: str, score: float = 0.5) -> Candidate:
    return Candidate(
        wine=wine(slug=slug, name=name),
        relative_path=f"{slug}.webp",
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
