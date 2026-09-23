from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class Settings:
    database_url: str
    max_upload_bytes: int
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
        max_upload_bytes=int(environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        visual_limit=int(environ.get("VISUAL_SHORTLIST_LIMIT", "50")),
    )
