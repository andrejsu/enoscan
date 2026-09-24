from os import environ


DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def load_database_url() -> str:
    return environ.get("DATABASE_URL") or (
        f"postgresql://{environ.get('PGUSER', 'vinolog')}:"
        f"{environ.get('PGPASSWORD', 'vinolog')}@"
        f"{environ.get('PGHOST', 'db')}:"
        f"{environ.get('PGPORT', '5432')}/"
        f"{environ.get('PGDATABASE', 'vinolog')}"
    )


def load_max_upload_bytes() -> int:
    return int(environ.get("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
