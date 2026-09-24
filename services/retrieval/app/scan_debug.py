"""Scan debug trace for the web result page's debug panel.

Turns the intermediate state app/ranking_main.py already holds — the
label_prep crop, the OCR pass, the visual retriever's shortlist and the
per-field ranking terms — into the ``debug`` object of the scan response
(apps/web's ScanDebug contract). Pure formatting: it never re-runs a stage
or changes a score.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np

from .catalog import Wine
from .label_fields import TEXT_FIELDS, RetrievalFields
from .ocr_retriever import OcrTrace
from .ranking import FIELD_WEIGHTS, RankingResult, field_breakdown


DEBUG_LIMIT = 10
THUMBNAIL_SIDE = 480
# Same cut ocr_retriever.OcrRetriever._fields applies before vocabulary search.
OCR_TEXT_MIN_CONFIDENCE = 40


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


def preprocessing_debug(source: np.ndarray, trace: OcrTrace) -> dict[str, object]:
    prepared = trace.prepared
    info = prepared.info
    label_px = info.get("label_px")
    return {
        "durationMs": trace.prepare_ms,
        "usedSam": prepared.used_sam,
        "warnings": list(prepared.warnings),
        "cropBox": list(prepared.crop_box) if prepared.crop_box else None,
        "images": {
            "source": image_data_url(source),
            "visual": image_data_url(prepared.visual),
            "ocr": image_data_url(prepared.ocr),
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


def ocr_debug(trace: OcrTrace) -> dict[str, object]:
    words = [word for label in trace.labels for word in label.words]
    errors = [label.error for label in trace.labels if label.error]
    return {
        "durationMs": trace.ocr_ms,
        "passes": ["crop", "full"][:len(trace.labels)],
        "text": " ".join(word.text for word in words if word.confidence >= OCR_TEXT_MIN_CONFIDENCE),
        "wordCount": len(words),
        "meanConfidence": round(sum(w.confidence for w in words) / len(words), 1) if words else None,
        "error": errors[0] if errors else None,
        "fields": [
            {
                "field": field,
                "weight": FIELD_WEIGHTS.get(field),
                "candidates": [{"value": c.value, "score": c.score} for c in getattr(trace.fields, field)],
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
