from __future__ import annotations

from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import StorageSettings


class ObjectStore:
    def __init__(self, settings: StorageSettings) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5, "mode": "standard"}),
        )

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError as error:
            if _status(error) != 404:
                raise
            self.client.create_bucket(Bucket=bucket)

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if _status(error) == 404:
                return False
            raise
        return True

    def put_bytes(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)

    def put_file(self, bucket: str, key: str, path: Path, content_type: str) -> None:
        self.client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})

    def get_bytes(self, bucket: str, key: str) -> bytes:
        return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        keys = self.list_keys(bucket, prefix)
        for start in range(0, len(keys), 1000):
            chunk = keys[start:start + 1000]
            self.client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": key} for key in chunk]})


def _status(error: ClientError) -> int:
    return int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
