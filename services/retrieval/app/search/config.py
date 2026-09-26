"""Settings for the ranking service (app/search/api.py).

Where to reach the OCR service (app/ocr/api.py) and the visual retriever
(app/visual/api.py). Ranking calls both over HTTP instead of loading OCR
models or the DINOv2 index in-process: each already runs as its own
long-lived service (see compose.yaml), and holding a second copy here only
doubles memory.
"""

from dataclasses import dataclass
from os import environ

from ..common.settings import load_database_url, load_max_upload_bytes
from .ranking import MIN_MARGIN


EVAL_POLICIES = ("matched", "top1")


@dataclass(frozen=True)
class SearchSettings:
    database_url: str
    max_upload_bytes: int
    ocr_base_url: str
    ocr_timeout: float
    retriever_base_url: str
    retriever_timeout: float
    min_margin: float
    eval_policy: str
    debug: bool


def load_search_settings() -> SearchSettings:
    return SearchSettings(
        database_url=load_database_url(),
        max_upload_bytes=load_max_upload_bytes(),
        ocr_base_url=environ.get("OCR_BASE_URL", "http://ocr-retriever:8000"),
        ocr_timeout=float(environ.get("OCR_TIMEOUT_SECONDS", "8")),
        retriever_base_url=environ.get("RETRIEVER_BASE_URL", "http://retriever:8000"),
        retriever_timeout=float(environ.get("RETRIEVER_TIMEOUT_SECONDS", "8")),
        min_margin=float(environ.get("RANKING_MIN_MARGIN", str(MIN_MARGIN))),
        eval_policy=_eval_policy(environ.get("RANKING_EVAL_POLICY", "matched")),
        debug=environ.get("RANKING_DEBUG", "true").lower() == "true",
    )


def _eval_policy(value: str) -> str:
    if value not in EVAL_POLICIES:
        raise ValueError(f"RANKING_EVAL_POLICY must be one of {EVAL_POLICIES}, got {value!r}")
    return value
