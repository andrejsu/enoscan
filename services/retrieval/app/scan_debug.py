"""Scan debug trace for the web result page's debug panel.

Turns what app/ranking_main.py already holds — the OCR service's words and
fields, the visual retriever's shortlist and the per-field ranking terms —
into the ``debug`` object of the scan response (apps/web's ScanDebug
contract). It never changes a score; the only stage it re-runs is
label_prep's crop, for the preprocessing thumbnails.
"""

from __future__ import annotations

import base64
import time

import cv2
import numpy as np

from .catalog import Wine
from .label_fields import TEXT_FIELDS, RetrievalFields
from .label_normalize import prepare_query
from .ocr.constants import SEARCH_TEXT_MIN_CONFIDENCE
from .ranking import FIELD_WEIGHTS, RankingResult, field_breakdown


DEBUG_LIMIT = 10
THUMBNAIL_SIDE = 480


def image_data_url(image: np.ndarray, *, max_side: int = THUMBNAIL_SIDE) -> str:
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError("Cannot encode debug thumbnail")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def _optional_number(info: dict, key: str) -> float | None:
    value = info.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def preprocessing_debug(source: np.ndarray) -> dict[str, object]:
    """label_prep's view of the photo — what the visual retriever searches.
    Recomputed here for the panel only; OCR reads the full frame."""
    started = time.perf_counter()
    prepared = prepare_query(source, fast=True)
    info = prepared.info
    label_px = info.get("label_px")
    return {
        "durationMs": round((time.perf_counter() - started) * 1000),
        "usedSam": prepared.used_sam,
        "warnings": list(prepared.warnings),
        "cropBox": list(prepared.crop_box) if prepared.crop_box else None,
        "images": {
            "source": image_data_url(source),
            "visual": image_data_url(prepared.visual),
            "ocr": image_data_url(source),
        },
        "metrics": {
            "labelWidth": label_px[0] if label_px else None,
            "labelHeight": label_px[1] if label_px else None,
            "sharpness": _optional_number(info, "sharpness"),
            "noiseSigma": _optional_number(info, "noise_sigma"),
            "glareFraction": _optional_number(info, "glare_frac"),
            "isDenoised": bool(info.get("denoised", False)),
        },
    }


def ocr_debug(payload: dict | None, error: str | None, duration_ms: int,
              fields: RetrievalFields) -> dict[str, object]:
    """``payload`` is the OCR service's response, None when the call failed."""
    words = (payload or {}).get("words", [])
    confidences = [word["confidence"] for word in words]
    return {
        "durationMs": duration_ms,
        "passes": ["full"] if payload else [],
        "text": " ".join(w["text"] for w in words if w["confidence"] >= SEARCH_TEXT_MIN_CONFIDENCE),
        "wordCount": len(words),
        "meanConfidence": round(sum(confidences) / len(confidences), 1) if confidences else None,
        "error": error,
        "fields": [
            {
                "field": field,
                "weight": FIELD_WEIGHTS.get(field),
                "candidates": [{"value": c.value, "score": c.score} for c in getattr(fields, field)[:DEBUG_LIMIT]],
            }
            for field in TEXT_FIELDS
        ],
    }


def retriever_debug(candidates: list[dict], error: str | None, duration_ms: int,
                    wines_by_slug: dict[str, Wine]) -> dict[str, object]:
    return {
        "durationMs": duration_ms,
        "error": error,
        "candidates": [
            {
                "slug": item["slug"],
                "score": item["score"],
                "goodMatches": item.get("goodMatches"),
                "inliers": item.get("inliers"),
                "wine": wines_by_slug[item["slug"]].as_card() if item["slug"] in wines_by_slug else None,
            }
            for item in candidates[:DEBUG_LIMIT]
        ],
    }


def ranking_debug(result: RankingResult, ocr_fields: RetrievalFields, visual_fields: RetrievalFields,
                  wines_by_slug: dict[str, Wine], threshold: float, duration_ms: int) -> dict[str, object]:
    ranked = sorted(result.evidence.items(), key=lambda item: item[1], reverse=True)[:DEBUG_LIMIT]
    return {
        "durationMs": duration_ms,
        "status": result.status,
        "score": result.score,
        "threshold": threshold,
        "candidates": [
            {
                "slug": slug,
                "score": score,
                "wine": wines_by_slug[slug].as_card(),
                "fields": [
                    {"field": item.field, "weight": item.weight, "score": item.score}
                    for item in field_breakdown(wines_by_slug[slug], ocr_fields, visual_fields)
                ],
            }
            for slug, score in ranked if slug in wines_by_slug
        ],
    }
