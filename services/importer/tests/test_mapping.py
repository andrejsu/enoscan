from importer.catalog_csv import CatalogWine
from importer.mapping import Mapping, SourceImage, mark_suspicious, media_stem, normalize_key, resolve_mappings


def wine(slug: str = "pino-nuar-2025", **overrides: object) -> CatalogWine:
    values: dict[str, object] = {
        "slug": slug,
        "name": "Пино Нуар, 2025",
        "category": "Вино",
        "color": "Красное",
        "region": "Крым",
        "grape_varieties": ("Пино Нуар",),
        "description": None,
        "winery": "Табия",
        "source_image_filename": "DSC00836.webp",
        "source_row_no": 1,
        "raw_record_count": 1,
    }
    values.update(overrides)
    return CatalogWine(**values)


def source(filename: str, sha: str, size: int = 100, width: int = 0, height: int = 0) -> SourceImage:
    return SourceImage(strapi_path=filename, filename=filename, image_sha256=sha, size_bytes=size,
                       width=width, height=height)


def test_media_stem_removes_strapi_hash() -> None:
    assert media_stem("DSC_00836_4070f8fd2f.webp") == "DSC_00836"


def test_normalize_key_ignores_filename_separators() -> None:
    assert normalize_key("DSC_00836") == normalize_key("dsc00836")


def test_prefers_image_filename_and_largest_file() -> None:
    result = resolve_mappings([wine()], [
        source("DSC_00836_4070f8fd2f.webp", "small", 10),
        source("DSC_00836_aaaaaaaaaa.webp", "large", 100),
    ])

    assert [(m.image_sha256, m.mapping_kind) for m in result] == [("large", "image_filename")]


def test_generic_filename_collision_prefers_the_bottle_shot() -> None:
    # Strapi archive: four uploads named Screenshot_9.webp; three are event banners.
    result = resolve_mappings([wine(source_image_filename="Screenshot_9.webp")], [
        source("Screenshot_9_384533e54c.webp", "banner", 78910, 905, 585),
        source("Screenshot_9_4bd676918f.webp", "fair", 47932, 976, 487),
        source("Screenshot_9_78adaf4455.webp", "bottle", 6312, 232, 465),
    ])

    assert result[0].image_sha256 == "bottle"


def test_portrait_uploads_keep_preferring_the_largest_file() -> None:
    # A padded packshot is barely portrait; a narrower rival must not win on shape alone.
    result = resolve_mappings([wine(source_image_filename="merlo.webp")], [
        source("merlo_89592556f7.webp", "narrow", 20000, 196, 604),
        source("merlo_d6c03313e4.webp", "padded", 90000, 1058, 1323),
    ])

    assert result[0].image_sha256 == "padded"


def test_same_shape_uploads_still_prefer_the_largest_file() -> None:
    result = resolve_mappings([wine(source_image_filename="Screenshot_19.webp")], [
        source("Screenshot_19_14834413ce.webp", "small", 5972, 278, 564),
        source("Screenshot_19_081d41ebac.webp", "large", 8260, 278, 564),
    ])

    assert result[0].image_sha256 == "large"


def test_falls_back_to_slug() -> None:
    result = resolve_mappings([wine(source_image_filename=None)], [source("pino-nuar-2025_4070f8fd2f.webp", "a")])

    assert result[0].mapping_kind == "slug"


def test_exact_matches_may_share_content_and_become_suspicious() -> None:
    first = wine("aaa-first", source_image_filename="label-one.webp")
    second = wine("bbb-second", source_image_filename="label-two.webp")

    result = mark_suspicious(resolve_mappings(
        [first, second], [source("label-one.webp", "same"), source("label-two.webp", "same")],
    ))

    assert [(m.slug, m.review_status) for m in result] == [("aaa-first", "suspicious"), ("bbb-second", "suspicious")]


def test_fuzzy_does_not_reuse_mapped_content() -> None:
    exact = wine("aaa-exact", source_image_filename="label.webp")
    fuzzy = wine("muskat-beloe-2021", name="Балаклава Мускат белое", winery="Балаклава",
                 source_image_filename="missing.webp")

    result = resolve_mappings([exact, fuzzy], [
        source("label.webp", "same"), source("balaklava_muskat_beloe_0123456789.webp", "same"),
    ])

    assert [m.slug for m in result] == ["aaa-exact"]


def test_fuzzy_match_uses_name_tokens() -> None:
    target = wine("muskat-beloe-2021", name="Балаклава Мускат белое", winery="Балаклава",
                  source_image_filename="missing.webp")

    result = resolve_mappings([target], [source("balaklava_muskat_beloe_0123456789.webp", "fuzzy")])

    assert result[0].mapping_kind == "fuzzy_filename"
    assert result[0].mapping_score >= 0.72


def test_suspicious_for_low_fuzzy_scores_but_not_confirmed() -> None:
    result = mark_suspicious([
        Mapping("a", "s1", "p", "fuzzy_filename", 0.8),
        Mapping("b", "s2", "p", "fuzzy_filename", 0.9),
        Mapping("c", "s3", "p", "slug", 0.1),
        Mapping("d", "s4", "p", "fuzzy_filename", 0.5, review_status="confirmed"),
    ])

    assert [m.review_status for m in result] == ["suspicious", "auto", "auto", "confirmed"]
