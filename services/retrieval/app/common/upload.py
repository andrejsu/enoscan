import numpy as np
from fastapi import HTTPException, UploadFile

from ..image_features import decode_image


ACCEPTED_IMAGE_TYPES = frozenset({"application/octet-stream", "image/jpeg", "image/png", "image/webp"})


async def read_image_upload(image: UploadFile, max_bytes: int) -> bytes:
    if image.content_type not in ACCEPTED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Поддерживаются JPEG, PNG и WebP.")
    content = await image.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Добавьте фотографию в поле image.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Размер фотографии не должен превышать 10 МБ.")
    return content


def decode_upload(content: bytes) -> np.ndarray:
    try:
        return decode_image(content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
