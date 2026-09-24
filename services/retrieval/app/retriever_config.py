"""Settings for the standalone retriever service (app/retriever_main.py).

Deliberately not app/config.py's Settings: that dataclass belongs to the
existing OCR-driven service (app/main.py) and this service's env vars/
defaults must be free to change without touching that one.
"""

from dataclasses import dataclass
from os import environ

from .common.settings import load_database_url, load_max_upload_bytes


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
    return RetrieverSettings(
        database_url=load_database_url(),
        max_upload_bytes=load_max_upload_bytes(),
        model_path=environ.get("MODEL_PATH", "/models/dinov2-small.onnx"),
        sam_model_dir=environ.get("SAM_MODEL_DIR", "/models/sam_vit_b_quant"),
        visual_limit=int(environ.get("VISUAL_SHORTLIST_LIMIT", "24")),
        embedding_limit=int(environ.get("EMBEDDING_SHORTLIST_LIMIT", "20")),
        query_sam=environ.get("QUERY_SAM", "false").lower() == "true",
    )
