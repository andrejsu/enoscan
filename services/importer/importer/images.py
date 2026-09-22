from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
import psycopg

from .archive import ArchiveMember
from .config import IMAGES_BUCKET
from .storage import ObjectStore
from .versioning import PREVIEW_VERSION


Image.MAX_IMAGE_PIXELS = 400_000_000

PREVIEW_BOX = (400, 600)
PREVIEW_QUALITY = 80
FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "MPO": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class DecodedImage:
    mime: str
    extension: str
    width: int
    height: int
    preview: bytes


def original_key(sha256: str, extension: str) -> str:
    return f"originals/{sha256[:2]}/{sha256}{extension}"


def preview_key(sha256: str) -> str:
    return f"previews/{PREVIEW_VERSION}/{sha256[:2]}/{sha256}.webp"


def decode_and_preview(content: bytes) -> DecodedImage:
    with Image.open(BytesIO(content)) as source:
        detected = FORMATS.get(source.format or "")
        if detected is None:
            raise ValueError(f"Unsupported image format: {source.format}")
        source.load()
        image = ImageOps.exif_transpose(source)
    width, height = image.size
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    preview = image.convert("RGBA" if has_alpha else "RGB")
    preview.thumbnail(PREVIEW_BOX, Image.Resampling.LANCZOS)
    output = BytesIO()
    preview.save(output, format="WEBP", quality=PREVIEW_QUALITY, method=4)
    return DecodedImage(mime=detected[0], extension=detected[1], width=width, height=height, preview=output.getvalue())


class ImageDecodeError(ValueError):
    pass


def ingest_image(member: ArchiveMember, store: ObjectStore, connection: psycopg.Connection,
                 archive_sha256: str) -> str:
    sha256 = hashlib.sha256(member.content).hexdigest()
    known = connection.execute("SELECT preview_version FROM images WHERE sha256 = %s", (sha256,)).fetchone()
    if known is None or known[0] != PREVIEW_VERSION:
        try:
            decoded = decode_and_preview(member.content)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
            raise ImageDecodeError(str(error)) from error
        object_key = original_key(sha256, decoded.extension)
        thumbnail_key = preview_key(sha256)
        if not store.exists(IMAGES_BUCKET, object_key):
            store.put_bytes(IMAGES_BUCKET, object_key, member.content, decoded.mime)
        if not store.exists(IMAGES_BUCKET, thumbnail_key):
            store.put_bytes(IMAGES_BUCKET, thumbnail_key, decoded.preview, "image/webp")
        connection.execute(
            """
            INSERT INTO images (sha256, object_key, preview_key, mime, width, height, size_bytes, preview_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sha256) DO UPDATE
            SET preview_key = EXCLUDED.preview_key, preview_version = EXCLUDED.preview_version
            """,
            (sha256, object_key, thumbnail_key, decoded.mime, decoded.width, decoded.height,
             len(member.content), PREVIEW_VERSION),
        )
    connection.execute(
        """
        INSERT INTO image_sources (strapi_path, filename, image_sha256, archive_sha256)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (strapi_path) DO UPDATE
        SET filename = EXCLUDED.filename, image_sha256 = EXCLUDED.image_sha256,
            archive_sha256 = EXCLUDED.archive_sha256
        """,
        (member.strapi_path, member.filename, sha256, archive_sha256),
    )
    return sha256
