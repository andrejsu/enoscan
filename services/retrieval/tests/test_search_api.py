from dataclasses import asdict, replace
from unittest.mock import patch

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from app.catalog.models import Wine
from app.evidence import FieldCandidate, RetrievalFields
from app.search import api
from app.search.ranking import RankingResult
from app.search.service import SearchService, evaluation_slug
from app.search.verification import LabelCheck


WINES = [Wine("rebus", "Ребус 2019", "Дивноморское"), Wine("kokur", "Кокур 2020", "Табия")]
OCR = {"fields": asdict(RetrievalFields(name=(FieldCandidate("Ребус 2019", 1.0),))),
       "words": [{"text": "Ребус", "confidence": 95.0, "bbox": [0, 0, 5, 5]}], "durationMs": 1, "engine": "test"}
VISUAL = {"candidates": [{"slug": "rebus", "score": 0.9}]}
IMAGE = cv2.imencode(".png", np.full((64, 64, 3), 200, dtype=np.uint8))[1].tobytes()


def producers(ocr, visual) -> httpx.AsyncClient:
    """The OCR service and the visual retriever over HTTP; None is a service that is down."""
    def respond(request: httpx.Request) -> httpx.Response:
        payload = ocr if str(request.url).startswith(api.settings.ocr_base_url) else visual
        if payload is None:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(respond))


def scan(ocr, visual, route="/v1/search", image=IMAGE):
    with patch.object(api, "service", SearchService(api.settings, WINES, "v1", producers(ocr, visual))):
        return TestClient(api.app).post(route, files={"image": ("a.png", image, "image/png")})


def test_ocr_and_visual_agree_on_a_match():
    body = scan(OCR, VISUAL).json()
    assert body["status"] == "matched" and body["wine"]["slug"] == "rebus"
    assert body["version"]["configuration"].endswith("ocr=test")


def test_ocr_service_down_degrades_to_visual_and_says_so():
    body = scan(None, VISUAL).json()
    assert body["candidates"][0]["slug"] == "rebus"
    assert body["debug"]["ocr"]["error"] == "ConnectError"


def test_both_services_down_is_an_infrastructure_error_not_not_found():
    assert scan(None, None).status_code == 503


UNSURE_VISUAL = {"candidates": [{"slug": "rebus", "score": 0.80}, {"slug": "kokur", "score": 0.799}]}


def test_eval_route_returns_the_same_top1_as_the_product_route():
    product = scan(OCR, VISUAL).json()
    evaluation = scan(OCR, VISUAL, "/v1/eval/predict")
    assert evaluation.status_code == 200
    assert evaluation.json() == {"slug": product["candidates"][0]["slug"]}


def test_eval_route_leaves_unsure_answer_empty_under_the_default_policy():
    assert scan(None, UNSURE_VISUAL).json()["status"] == "not_found"
    assert scan(None, UNSURE_VISUAL, "/v1/eval/predict").json() == {"slug": ""}


def test_eval_route_answers_unsure_top1_under_top1_policy():
    with patch.object(api, "settings", replace(api.settings, eval_policy="top1")):
        assert scan(None, UNSURE_VISUAL, "/v1/eval/predict").json() == {"slug": "rebus"}


def test_eval_route_rejects_a_broken_file_and_reports_outages():
    assert scan(OCR, VISUAL, "/v1/eval/predict", image=b"not an image").status_code == 422
    assert scan(None, None, "/v1/eval/predict").status_code == 503


def test_openapi_documents_the_upload_field_and_both_scan_responses():
    spec = api.app.openapi()
    for path in ("/v1/search", "/v1/eval/predict"):
        operation = spec["paths"][path]["post"]
        assert "multipart/form-data" in operation["requestBody"]["content"]
        assert {"200", "415", "422", "503"} <= set(operation["responses"])
    assert set(spec["components"]["schemas"]["EvaluationPrediction"]["properties"]) == {"slug"}
    assert "recommendations" in spec["components"]["schemas"]["ScanResponse"]["properties"]


def test_top1_policy_answers_only_a_wine_the_label_does_not_contradict():
    checked = (LabelCheck("rebus", (), "sweetness", "на этикетке брют, в каталоге сухое"),)
    result = RankingResult("not_found", None, 0.3, 0.0, {"rebus": 0.3, "kokur": 0.1}, {"rebus": "…"}, checked)
    # «kokur» is first once rejected wines go last, but nobody checked it against the label.
    assert evaluation_slug(result, "top1") == ""
    passed = checked + (LabelCheck("kokur", ()),)
    assert evaluation_slug(replace(result, checks=passed), "top1") == "kokur"
