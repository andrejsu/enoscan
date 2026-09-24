from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..catalog import load_wines
from ..common.settings import load_database_url, load_max_upload_bytes
from ..common.upload import decode_upload, read_image_upload
from .engine import ENGINE_NAME, load_engine
from .retriever import OcrRetriever
from .vocabulary import FieldVocabulary


database_url = load_database_url()
max_upload_bytes = load_max_upload_bytes()
retriever: OcrRetriever | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global retriever
    load_engine()
    retriever = OcrRetriever(FieldVocabulary(load_wines(database_url)))
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
    decoded = decode_upload(await read_image_upload(image, max_upload_bytes))
    trace = await run_in_threadpool(retriever.trace, decoded)
    return {
        "fields": asdict(trace.fields),
        "words": [{"text": w.text, "confidence": w.confidence, "bbox": list(w.bbox)} for w in trace.label.words],
        "durationMs": trace.ocr_ms,
        "engine": ENGINE_NAME,
    }
