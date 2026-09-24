import pytest

from app.catalog import Wine
from app.label_fields import FieldCandidate, RetrievalFields
from app.ranking import MATCH_THRESHOLD, field_breakdown, rank


def wine(slug="rebus-2019", name="Ребус 2019", winery="Дивноморское", **overrides):
    values = dict(slug=slug, name=name, winery=winery,
                  category="Вино", color="Красное", region="Крым", grape_varieties=("Пино Нуар",))
    values.update(overrides)
    return Wine(**values)


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
    assert result.score > MATCH_THRESHOLD


def test_missing_optional_fields_do_not_drag_down_the_score():
    target = wine()
    ocr_fields = RetrievalFields(
        name=(FieldCandidate(target.name, 1.0),),
        winery=(FieldCandidate(target.winery, 1.0),),
        # year/grape_varieties/etc. left empty: OCR found no evidence for them at all
    )
    result = rank(ocr_fields, RetrievalFields(), [target])
    assert result.score == pytest.approx(1.0)


def test_visual_only_evidence_can_match_without_any_ocr_text():
    target = wine()
    visual_fields = RetrievalFields(slug=(FieldCandidate(target.slug, 0.9),))
    result = rank(RetrievalFields(), visual_fields, [target])
    assert result.status == "matched"
    assert result.slug == target.slug


def test_score_at_or_below_threshold_is_an_honest_not_found():
    target = wine()
    visual_fields = RetrievalFields(slug=(FieldCandidate(target.slug, MATCH_THRESHOLD),))
    result = rank(RetrievalFields(), visual_fields, [target], threshold=MATCH_THRESHOLD)
    assert result.status == "not_found"
    assert result.slug is None


def test_no_catalog_wines_is_not_found():
    result = rank(RetrievalFields(), RetrievalFields(), [])
    assert result.status == "not_found"
    assert result.slug is None


def test_field_breakdown_explains_the_score_and_skips_fields_without_evidence():
    target = wine()
    ocr_fields = RetrievalFields(
        name=(FieldCandidate(target.name, 0.8),),
        winery=(FieldCandidate("Табия", 1.0),),
    )
    visual_fields = RetrievalFields(slug=(FieldCandidate(target.slug, 0.6),))
    breakdown = {item.field: item for item in field_breakdown(target, ocr_fields, visual_fields)}
    assert set(breakdown) == {"name", "winery", "slug"}
    assert breakdown["name"].score == 0.8
    assert breakdown["winery"].score == 0.0  # evidence exists, but for another winery
    total_weight = sum(item.weight for item in breakdown.values())
    expected = sum(item.weight * item.score for item in breakdown.values()) / total_weight
    result = rank(ocr_fields, visual_fields, [target])
    assert result.score == pytest.approx(expected, abs=1e-4)
