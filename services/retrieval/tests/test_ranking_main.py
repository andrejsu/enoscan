from dataclasses import asdict
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app import ranking_main
from app.catalog import Wine
from app.label_fields import FieldCandidate, RetrievalFields


WINES = [Wine("rebus", "Ребус 2019", "Дивноморское"), Wine("kokur", "Кокур 2020", "Табия")]
OCR = {"fields": asdict(RetrievalFields(name=(FieldCandidate("Ребус 2019", 1.0),))),
       "words": [{"text": "Ребус", "confidence": 95.0, "bbox": [0, 0, 5, 5]}], "durationMs": 1, "engine": "test"}
VISUAL = {"candidates": [{"slug": "rebus", "score": 0.9}]}
IMAGE = cv2.imencode(".png", np.full((64, 64, 3), 200, dtype=np.uint8))[1].tobytes()


def scan(ocr, visual):
    async def post_image(base_url, *args):
        response = ocr if base_url == ranking_main.settings.ocr_base_url else visual
        return (response, None, 3) if response else (None, "ConnectError", 3)

    with patch.object(ranking_main, "load_wines", return_value=WINES), \
         patch.object(ranking_main, "current_dataset_version", return_value="v1"), \
         patch.object(ranking_main, "_post_image", post_image), \
         TestClient(ranking_main.app) as client:
        return client.post("/v1/search", files={"image": ("a.png", IMAGE, "image/png")})


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
