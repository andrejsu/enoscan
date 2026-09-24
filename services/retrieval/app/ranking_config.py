"""Settings for the standalone ranking service (app/ranking_main.py).

Where to reach the OCR service (app/ocr/main.py) and the visual retriever
(app/retriever_main.py). Ranking calls both over HTTP instead of loading
OCR models or the DINOv2 index in-process: each already runs as its own
long-lived service (see compose.yaml), and holding a second copy here only
doubles memory.
"""

from dataclasses import dataclass
from os import environ

from .common.settings import load_database_url, load_max_upload_bytes
from .ranking import MATCH_THRESHOLD


@dataclass(frozen=True)
class RankingSettings:
    database_url: str
    max_upload_bytes: int
    ocr_base_url: str
    ocr_timeout: float
    retriever_base_url: str
    retriever_timeout: float
    match_threshold: float
    debug: bool  # attach the per-stage debug trace to every /v1/search response


def load_ranking_settings() -> RankingSettings:
    return RankingSettings(
        database_url=load_database_url(),
        max_upload_bytes=load_max_upload_bytes(),
        ocr_base_url=environ.get("OCR_BASE_URL", "http://ocr-retriever:8000"),
        ocr_timeout=float(environ.get("OCR_TIMEOUT_SECONDS", "8")),
        retriever_base_url=environ.get("RETRIEVER_BASE_URL", "http://retriever:8000"),
        retriever_timeout=float(environ.get("RETRIEVER_TIMEOUT_SECONDS", "8")),
        match_threshold=float(environ.get("RANKING_MATCH_THRESHOLD", str(MATCH_THRESHOLD))),
        debug=environ.get("RANKING_DEBUG", "true").lower() == "true",
    )
