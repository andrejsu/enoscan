from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path

import boto3
from botocore.config import Config


IMAGES_BUCKET = "vinolog-images"
INDEXES_BUCKET = "vinolog-indexes"


@dataclass(frozen=True)
class StorageSettings:
    endpoint: str
    access_key: str
    secret_key: str
    region: str


def storage_from_environment() -> StorageSettings:
    return StorageSettings(
        endpoint=environ.get("S3_ENDPOINT", "http://minio:9000"),
        access_key=environ.get("S3_ACCESS_KEY", "vinolog"),
        secret_key=environ.get("S3_SECRET_KEY", "vinolog-secret"),
        region=environ.get("S3_REGION", "us-east-1"),
    )


class ObjectStore:
    def __init__(self, settings: StorageSettings | None = None) -> None:
        settings = settings or storage_from_environment()
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5, "mode": "standard"}),
        )

    def get_bytes(self, bucket: str, key: str) -> bytes:
        return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def download_file(self, bucket: str, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(bucket, key, str(destination))

    def put_file(self, bucket: str, key: str, path: Path) -> None:
        self.client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "application/octet-stream"})
