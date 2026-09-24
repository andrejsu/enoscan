from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .catalog import load_wines
from .field_vocabulary import FieldVocabulary
from .image_features import decode_image
from .ocr import ENGINE_NAME, load_engine
from .ocr_config import load_ocr_settings
from .ocr_retriever import OcrRetriever


ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}

settings = load_ocr_settings()
retriever: OcrRetriever | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global retriever
    load_engine()
    retriever = OcrRetriever(FieldVocabulary(load_wines(settings.database_url)))
    yield
    retriever = None


app = FastAPI(title="Vinolog OCR field retriever (standalone)", version="0.2.0", lifespan=lifespan)


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

    trace = await run_in_threadpool(retriever.trace, decoded)
    return {
        "fields": asdict(trace.fields),
        "words": [{"text": w.text, "confidence": w.confidence, "bbox": list(w.bbox)} for w in trace.label.words],
        "durationMs": trace.ocr_ms,
        "engine": ENGINE_NAME,
    }
