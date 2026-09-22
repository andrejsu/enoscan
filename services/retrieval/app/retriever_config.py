"""Settings for the standalone retriever service (app/retriever_main.py).

Deliberately not app/config.py's Settings: that dataclass belongs to the
existing OCR-driven service (app/main.py) and this service's env vars/
defaults must be free to change without touching that one. Some duplication
(DB URL assembly) is the accepted cost of the isolation.
"""

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class RetrieverSettings:
    database_url: str
    max_upload_bytes: int
    model_path: str
    sam_model_dir: str
    visual_limit: int
    embedding_limit: int
    query_sam: bool


def load_retriever_settings() -> RetrieverSettings:
    database_url = environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
            f"{environ.get('PGPASSWORD', 'vinolog')}@"
            f"{environ.get('PGHOST', 'db')}:"
            f"{environ.get('PGPORT', '5432')}/"
            f"{environ.get('PGDATABASE', 'vinolog')}"
        )

    return RetrieverSettings(
        database_url=database_url,
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        model_path=environ.get("MODEL_PATH", "/models/dinov2-small.onnx"),
        sam_model_dir=environ.get("SAM_MODEL_DIR", "/models/sam_vit_b_quant"),
        visual_limit=int(environ.get("VISUAL_SHORTLIST_LIMIT", "24")),
        embedding_limit=int(environ.get("EMBEDDING_SHORTLIST_LIMIT", "20")),
        query_sam=environ.get("QUERY_SAM", "false").lower() == "true",
    )
