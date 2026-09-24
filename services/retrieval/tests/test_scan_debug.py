import numpy as np

from app.catalog import Wine
from app.label_fields import TEXT_FIELDS, FieldCandidate, RetrievalFields
from app.label_normalize import PreparedQuery
from app.ocr import OcrResult, OcrWord
from app.ocr_retriever import OcrTrace
from app.ranking import rank
from app.scan_debug import DEBUG_LIMIT, ocr_debug, preprocessing_debug, ranking_debug, retriever_debug


def wine(slug, name="Ребус 2019", winery="Дивноморское"):
    return Wine(slug=slug, name=name, winery=winery, category="Вино", color="Красное",
                region="Крым", grape_varieties=("Пино Нуар",))


def trace(labels=(OcrResult((OcrWord("Ребус", 90, (0, 0, 10, 10), (1, 1, 1)),
                              OcrWord("шум", 12, (0, 0, 10, 10), (1, 1, 1)))),)):
    prepared = PreparedQuery(visual=np.full((40, 60, 3), 200, dtype=np.uint8),
                             ocr=np.full((40, 60), 200, dtype=np.uint8), used_sam=False,
                             warnings=["sam_skipped"], info={"label_px": [60, 40], "sharpness": 12.5,
                                                            "noise_sigma": 1.2, "glare_frac": 0.01},
                             crop_box=(0.05, 0.3, 0.95, 0.95))
    fields = RetrievalFields(name=(FieldCandidate("Ребус 2019", 0.9),))
    return OcrTrace(fields, prepared, labels, prepare_ms=7, ocr_ms=300)


def test_preprocessing_debug_embeds_thumbnails_and_label_prep_metrics():
    debug = preprocessing_debug(np.zeros((2000, 1000, 3), dtype=np.uint8), trace())
    assert debug["durationMs"] == 7
    assert debug["cropBox"] == [0.05, 0.3, 0.95, 0.95]
    assert all(url.startswith("data:image/jpeg;base64,") for url in debug["images"].values())
    assert debug["metrics"] == {"labelWidth": 60, "labelHeight": 40, "sharpness": 12.5,
                                "noiseSigma": 1.2, "glareFraction": 0.01, "isDenoised": False}


def test_ocr_debug_lists_every_field_even_without_candidates():
    debug = ocr_debug(trace())
    assert [item["field"] for item in debug["fields"]] == list(TEXT_FIELDS)
    assert debug["fields"][0]["candidates"] == [{"value": "Ребус 2019", "score": 0.9}]
    assert debug["text"] == "Ребус"  # low-confidence words are not searched, so not shown as searched text
    assert debug["wordCount"] == 2
    assert debug["passes"] == ["crop"]
    assert debug["error"] is None


def test_ocr_debug_reports_the_tesseract_error():
    debug = ocr_debug(trace(labels=(OcrResult(error="timeout", passes=0),)))
    assert debug["error"] == "timeout"
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
    visual_fields = RetrievalFields(slug=(FieldCandidate("w3", 0.8), FieldCandidate("w5", 0.9)))
    result = rank(ocr_fields, visual_fields, wines, threshold=0.45)
    debug = ranking_debug(result, ocr_fields, visual_fields, by_slug, 0.45, 3)
    scores = [item["score"] for item in debug["candidates"]]
    assert len(scores) == DEBUG_LIMIT and scores == sorted(scores, reverse=True)
    assert debug["candidates"][0]["slug"] == "w3"
    assert {term["field"] for term in debug["candidates"][0]["fields"]} == {"name", "slug"}
    assert debug["status"] == result.status and debug["threshold"] == 0.45
    assert debug["durationMs"] == 3
