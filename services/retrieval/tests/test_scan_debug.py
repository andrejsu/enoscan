from dataclasses import asdict

import numpy as np

from app.catalog import Wine
from app.label_fields import TEXT_FIELDS, FieldCandidate, RetrievalFields, fields_from_json
from app.ranking import rank
from app.scan_debug import DEBUG_LIMIT, ocr_debug, preprocessing_debug, ranking_debug, retriever_debug


def wine(slug, name="Ребус 2019", winery="Дивноморское"):
    return Wine(slug=slug, name=name, winery=winery, category="Вино", color="Красное",
                region="Крым", grape_varieties=("Пино Нуар",))


FIELDS = RetrievalFields(name=(FieldCandidate("Ребус 2019", 0.9),))
PAYLOAD = {"fields": asdict(FIELDS), "durationMs": 300, "engine": "test",
           "words": [{"text": "Ребус", "confidence": 90.0, "bbox": [0, 0, 10, 10]},
                     {"text": "шум", "confidence": 12.0, "bbox": [0, 0, 10, 10]}]}


def test_preprocessing_debug_embeds_thumbnails_and_label_prep_metrics():
    debug = preprocessing_debug(np.full((2000, 1000, 3), 200, dtype=np.uint8))
    assert debug["durationMs"] >= 0
    assert debug["cropBox"] == [0.05, 0.3, 0.95, 0.95]
    assert all(url.startswith("data:image/jpeg;base64,") for url in debug["images"].values())
    assert set(debug["metrics"]) == {"labelWidth", "labelHeight", "sharpness", "noiseSigma",
                                     "glareFraction", "isDenoised"}


def test_fields_survive_the_json_round_trip_between_services():
    assert fields_from_json(PAYLOAD["fields"]) == FIELDS


def test_ocr_debug_lists_every_field_even_without_candidates():
    debug = ocr_debug(PAYLOAD, None, 320, FIELDS)
    assert [item["field"] for item in debug["fields"]] == list(TEXT_FIELDS)
    assert debug["fields"][0]["candidates"] == [{"value": "Ребус 2019", "score": 0.9}]
    assert debug["text"] == "Ребус"  # low-confidence words are not searched, so not shown as searched text
    assert debug["wordCount"] == 2
    assert debug["passes"] == ["full"]
    assert debug["durationMs"] == 320
    assert debug["error"] is None


def test_ocr_debug_reports_an_unreachable_ocr_service():
    debug = ocr_debug(None, "ConnectError", 5, RetrievalFields())
    assert debug["error"] == "ConnectError"
    assert debug["passes"] == [] and debug["wordCount"] == 0
    assert debug["meanConfidence"] is None


def test_retriever_debug_keeps_ten_and_survives_unknown_slugs():
    wines = {"a": wine("a")}
    raw = [{"slug": "a", "score": 0.5, "goodMatches": 12, "inliers": 8}] + \
          [{"slug": f"gone-{i}", "score": 0.1} for i in range(15)]
    debug = retriever_debug(raw, None, 900, wines)
    assert len(debug["candidates"]) == DEBUG_LIMIT
    assert debug["candidates"][0]["wine"]["slug"] == "a"
    assert debug["candidates"][1]["wine"] is None
    assert debug["candidates"][1]["inliers"] is None


def test_ranking_debug_sorts_top_ten_with_field_terms():
    wines = [wine(f"w{i}", name=f"Вино {i}", winery=f"Винодельня {i}") for i in range(15)]
    by_slug = {item.slug: item for item in wines}
    ocr_fields = RetrievalFields(name=(FieldCandidate("Вино 3", 1.0),))
    visual_fields = RetrievalFields(slug=(FieldCandidate("w3", 0.9), FieldCandidate("w5", 0.8)))
    result = rank(ocr_fields, visual_fields, wines, min_margin=0.06)
    debug = ranking_debug(result, ocr_fields, visual_fields, by_slug, 0.06, 3)
    scores = [item["score"] for item in debug["candidates"]]
    assert len(scores) == DEBUG_LIMIT and scores == sorted(scores, reverse=True)
    assert debug["candidates"][0]["slug"] == "w3"
    assert {term["field"] for term in debug["candidates"][0]["fields"]} == {"name", "slug"}
    assert debug["status"] == result.status and debug["minMargin"] == 0.06
    assert debug["margin"] == result.margin
    assert debug["durationMs"] == 3
