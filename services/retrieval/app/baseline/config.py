"""Settings of the legacy SIFT baseline (compose service `retrieval`): a purely
visual SIFT/RANSAC search behind neither the scanner nor the evaluation route,
kept for scripts/eval.py and scripts/eval_search.py."""

from dataclasses import dataclass
from os import environ

from ..common.settings import load_database_url, load_max_upload_bytes
from ..sift_index import SiftSearchConfig


SIFT_INDEX_KIND = "sift-v3"
SIFT_CONFIG = SiftSearchConfig(trees=4, checks=64, feature_count=1400)


@dataclass(frozen=True)
class Settings:
    database_url: str
    max_upload_bytes: int
    visual_limit: int = 50


def load_settings() -> Settings:
    return Settings(
        database_url=load_database_url(),
        max_upload_bytes=load_max_upload_bytes(),
        visual_limit=int(environ.get("VISUAL_SHORTLIST_LIMIT", "50")),
    )
