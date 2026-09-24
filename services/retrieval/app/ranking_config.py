"""Settings for the standalone ranking service (app/ranking_main.py).

Loads the OCR field extractor's own settings plus where to reach the
visual retriever service. Ranking calls app/retriever_main.py over HTTP
instead of loading its own RetrieverIndex/Dinov2Encoder in-process: both
services independently holding the DINOv2 model + full visual index
doubled that memory footprint for no benefit, since retriever already
runs as its own long-lived service (see compose.yaml's `retriever`).
"""

from dataclasses import dataclass
from os import environ

from .ranking import MATCH_THRESHOLD


@dataclass(frozen=True)
class RankingSettings:
    database_url: str
    max_upload_bytes: int
    ocr_timeout: float
    ocr_psm: int
    ocr_preprocess: bool
    ocr_retry: bool
    retriever_base_url: str
    retriever_timeout: float
    match_threshold: float
    debug: bool  # attach the per-stage debug trace to every /v1/search response


def load_ranking_settings() -> RankingSettings:
    database_url = environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
            f"{environ.get('PGPASSWORD', 'vinolog')}@"
            f"{environ.get('PGHOST', 'db')}:"
            f"{environ.get('PGPORT', '5432')}/"
            f"{environ.get('PGDATABASE', 'vinolog')}"
        )

    return RankingSettings(
        database_url=database_url,
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        ocr_timeout=float(environ.get("OCR_TIMEOUT_SECONDS", "2")),
        ocr_psm=int(environ.get("OCR_PSM", "6")),
        ocr_preprocess=environ.get("OCR_PREPROCESS", "true").lower() == "true",
        ocr_retry=environ.get("OCR_RETRY", "false").lower() == "true",
        retriever_base_url=environ.get("RETRIEVER_BASE_URL", "http://retriever:8000"),
        retriever_timeout=float(environ.get("RETRIEVER_TIMEOUT_SECONDS", "8")),
        match_threshold=float(environ.get("RANKING_MATCH_THRESHOLD", str(MATCH_THRESHOLD))),
        debug=environ.get("RANKING_DEBUG", "true").lower() == "true",
    )
