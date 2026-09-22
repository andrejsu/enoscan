from dataclasses import dataclass
from os import environ
from pathlib import Path


IMAGES_BUCKET = "vinolog-images"
INDEXES_BUCKET = "vinolog-indexes"
EVAL_BUCKET = "vinolog-eval"
BUCKETS = (IMAGES_BUCKET, INDEXES_BUCKET, EVAL_BUCKET)

CATALOG_FILENAME = "strapi_output0709.csv"
ARCHIVE_FILENAMES = (
    "prod-svoe-vino-strapi.part1.rar",
    "prod-svoe-vino-strapi.part2.rar",
    "prod-svoe-vino-strapi.part3.rar",
)
EVAL_ARCHIVES = {
    "eval": "eval.zip",
    "real-photos": "Реальные фото.zip",
}


@dataclass(frozen=True)
class StorageSettings:
    endpoint: str
    access_key: str
    secret_key: str
    region: str


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage: StorageSettings
    input_dir: Path
    migrations_dir: Path
    overrides_path: Path


def database_url_from_environment() -> str:
    database_url = environ.get("DATABASE_URL")
    if database_url:
        return database_url
    return (
        f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
        f"{environ.get('PGPASSWORD', 'vinolog')}@"
        f"{environ.get('PGHOST', 'db')}:"
        f"{environ.get('PGPORT', '5432')}/"
        f"{environ.get('PGDATABASE', 'vinolog')}"
    )


def storage_from_environment() -> StorageSettings:
    return StorageSettings(
        endpoint=environ.get("S3_ENDPOINT", "http://minio:9000"),
        access_key=environ.get("S3_ACCESS_KEY", "vinolog"),
        secret_key=environ.get("S3_SECRET_KEY", "vinolog-secret"),
        region=environ.get("S3_REGION", "us-east-1"),
    )


def load_settings() -> Settings:
    db_dir = Path(environ.get("DB_DIR", "/db"))
    return Settings(
        database_url=database_url_from_environment(),
        storage=storage_from_environment(),
        input_dir=Path(environ.get("INPUT_DIR", "/input")),
        migrations_dir=db_dir / "migrations",
        overrides_path=db_dir / "image-overrides.csv",
    )
