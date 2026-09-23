"""Standalone OCR field-extraction service — the existing Tesseract-driven
label reader (app/ocr.py) plus catalog-vocabulary fuzzy matching
(app/field_vocabulary.py), detached from app/main.py (the now-visual-only
scanner) the same way app/retriever_main.py detached the visual pipeline.
Imports nothing from app/service.py, app/main.py or app/index.py.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, HTTPException, UploadFile

from .catalog import load_wines
from .field_vocabulary import FieldVocabulary
from .image_features import decode_image
from .ocr_config import load_ocr_settings
from .ocr_retriever import OcrRetriever


ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}

settings = load_ocr_settings()
retriever: OcrRetriever | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global retriever
    wines = load_wines(settings.database_url)
    retriever = OcrRetriever(FieldVocabulary(wines), ocr_options=dict(
        timeout=settings.ocr_timeout, psm=settings.ocr_psm,
        preprocess=settings.ocr_preprocess, retry=settings.ocr_retry,
    ))
    yield
    retriever = None


app = FastAPI(title="Vinolog OCR field retriever (standalone)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if retriever else "loading"}


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Словарь полей ещё загружается.")
    if image.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="Поддерживаются JPEG, PNG и WebP.")
    content = await image.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Добавьте фотографию в поле image.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Размер фотографии не должен превышать 10 МБ.")
    try:
        decoded = decode_image(content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return asdict(retriever.extract(decoded))
