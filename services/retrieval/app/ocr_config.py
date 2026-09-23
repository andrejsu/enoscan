"""Settings for the standalone OCR retriever service (app/ocr_main.py).

Deliberately not app/config.py's Settings: that dataclass belongs to the
now-visual-only main scanner (app/main.py), and this service's env vars/
defaults must be free to change without touching that one — the same
isolation app/retriever_config.py keeps from app/config.py.
"""

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class OcrRetrieverSettings:
    database_url: str
    max_upload_bytes: int
    ocr_timeout: float
    ocr_psm: int
    ocr_preprocess: bool
    ocr_retry: bool


def load_ocr_settings() -> OcrRetrieverSettings:
    database_url = environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
            f"{environ.get('PGPASSWORD', 'vinolog')}@"
            f"{environ.get('PGHOST', 'db')}:"
            f"{environ.get('PGPORT', '5432')}/"
            f"{environ.get('PGDATABASE', 'vinolog')}"
        )

    return OcrRetrieverSettings(
        database_url=database_url,
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        ocr_timeout=float(environ.get("OCR_TIMEOUT_SECONDS", "2")),
        ocr_psm=int(environ.get("OCR_PSM", "6")),
        ocr_preprocess=environ.get("OCR_PREPROCESS", "true").lower() == "true",
        ocr_retry=environ.get("OCR_RETRY", "false").lower() == "true",
    )
