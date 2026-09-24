from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class OcrRetrieverSettings:
    database_url: str
    max_upload_bytes: int


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
    )
