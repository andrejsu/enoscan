from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class Settings:
    database_url: str
    dataset_root: str
    index_path: str
    max_upload_bytes: int
    ocr_timeout: float = 2.0
    ocr_psm: int = 6
    ocr_preprocess: bool = True
    ocr_retry: bool = False
    visual_limit: int = 50


def load_settings() -> Settings:
    database_url = environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
            f"{environ.get('PGPASSWORD', 'vinolog')}@"
            f"{environ.get('PGHOST', 'db')}:"
            f"{environ.get('PGPORT', '5432')}/"
            f"{environ.get('PGDATABASE', 'vinolog')}"
        )

    return Settings(
        database_url=database_url,
        dataset_root=environ.get("DATASET_ROOT", "/dataset/current"),
        index_path=environ.get("INDEX_PATH", "/indexes/sift-v1.npz"),
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        ocr_timeout=float(environ.get("OCR_TIMEOUT_SECONDS", "2")),
        ocr_psm=int(environ.get("OCR_PSM", "6")),
        ocr_preprocess=environ.get("OCR_PREPROCESS", "true").lower() == "true",
        ocr_retry=environ.get("OCR_RETRY", "false").lower() == "true",
        visual_limit=int(environ.get("VISUAL_SHORTLIST_LIMIT", "50")),
    )
