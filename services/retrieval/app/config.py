from dataclasses import dataclass
from os import environ

from .common.settings import load_database_url, load_max_upload_bytes


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
