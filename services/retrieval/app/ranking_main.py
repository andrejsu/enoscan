"""Standalone ranking service — the one place that combines OCR field
evidence (app/ocr_retriever.py) and visual slug evidence (app/retriever.py)
into a single resolved wine, via app/ranking.py. Imports nothing from
app/service.py, app/main.py or app/index.py — the main scanner stays
untouched and unrelated.

The visual side is fetched over HTTP from the retriever service
(app/retriever_main.py) rather than loaded in-process: both services
independently holding the DINOv2 model + full visual index in memory
(~1.3-2.2GB each) was enough to push the whole compose stack into
OOM restart loops. retriever already runs continuously as its own
service — ranking just calls it.
"""

import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile

from .catalog import Wine, current_dataset_version, load_wines
from .field_vocabulary import FieldVocabulary
from .image_features import decode_image
from .label_fields import FieldCandidate, RetrievalFields
from .ocr_retriever import OcrRetriever
from .ranking import rank
from .ranking_config import load_ranking_settings
from .scan_debug import ocr_debug, preprocessing_debug, ranking_debug, retriever_debug


# Same response contract as app/service.py and app/retriever_main.py
# (apps/web's #shared/contracts ScanResponse) — this is the one service
# meant to sit behind the product's scanner, so it must speak the same
# shape they do, not a leaner one-off.
ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}
RESPONSE_LIMIT = 5

# Retry with OcrRetriever.extract_deep() (one more Tesseract pass, over the
# raw uncropped image) only for a near-miss not_found — score below
# threshold but within this band of it. Deliberately one-sided: retrying
# an already-matched result doesn't rescue anything and only adds risk —
# the extra pass sees more background clutter (no crop), which measurably
# raised the odds of a *new* coincidental false match on an already-correct
# case (abrau-dyurso flipped to a wrong wine when tried against an
# already-matched 0.55). Calibrated the same way as MATCH_THRESHOLD
# (app/ranking.py): zhemchuzhnaya-9-aligote-czitron's honest not_found sat
# at 0.32 against a 0.45 threshold — comfortably inside a 0.15 band.
BORDERLINE_BAND = 0.15

settings = load_ranking_settings()
ocr_retriever: OcrRetriever | None = None
retriever_client: httpx.AsyncClient | None = None
wines_by_slug: dict[str, Wine] = {}
dataset_version = "unversioned"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global dataset_version, ocr_retriever, retriever_client, wines_by_slug
    dataset_version = current_dataset_version(settings.database_url)
    wines = load_wines(settings.database_url)
    wines_by_slug = {wine.slug: wine for wine in wines}
    ocr_retriever = OcrRetriever(FieldVocabulary(wines), ocr_options=dict(
        timeout=settings.ocr_timeout, psm=settings.ocr_psm,
        preprocess=settings.ocr_preprocess, retry=settings.ocr_retry,
    ))
    retriever_client = httpx.AsyncClient(base_url=settings.retriever_base_url)
    yield
    await retriever_client.aclose()
    ocr_retriever = None
    retriever_client = None
    wines_by_slug = {}


app = FastAPI(title="Vinolog ranking (standalone)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if (ocr_retriever and retriever_client) else "loading"}


async def _visual_fields(content: bytes, content_type: str | None,
                         filename: str | None) -> tuple[RetrievalFields, list[dict], str | None]:
    """Ask retriever for its top slug candidates. A slow/unreachable
    retriever degrades to OCR-only ranking rather than failing the whole
    request — the same "expected OCR failure leaves visual search" spirit
    app/service.py used to have, just inverted. Also returns the raw
    candidates and the failure reason, for the debug trace."""
    try:
        response = await retriever_client.post(
            "/v1/search",
            files={"image": (filename or "image", content, content_type or "application/octet-stream")},
            timeout=settings.retriever_timeout,
        )
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
    except httpx.HTTPError as error:
        return RetrievalFields(), [], type(error).__name__
    fields = RetrievalFields(slug=tuple(FieldCandidate(c["slug"], c["score"]) for c in candidates))
    return fields, candidates, None


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if ocr_retriever is None or retriever_client is None:
        raise HTTPException(status_code=503, detail="Ранжирование ещё загружается.")
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

    started = time.perf_counter()
    ocr_started = time.perf_counter()
    ocr_trace = ocr_retriever.trace(decoded)
    ocr_fields = ocr_trace.fields
    ocr_ms = round((time.perf_counter() - ocr_started) * 1000)

    visual_started = time.perf_counter()
    visual_fields, visual_candidates, visual_error = await _visual_fields(
        content, image.content_type, image.filename)
    visual_ms = round((time.perf_counter() - visual_started) * 1000)

    wines = list(wines_by_slug.values())
    rank_started = time.perf_counter()
    result = rank(ocr_fields, visual_fields, wines, threshold=settings.match_threshold)
    rank_ms = round((time.perf_counter() - rank_started) * 1000)

    retry_ms = 0
    if result.status == "not_found" and settings.match_threshold - result.score <= BORDERLINE_BAND:
        retry_started = time.perf_counter()
        ocr_trace = ocr_retriever.trace(decoded, deep=True)
        ocr_fields = ocr_trace.fields
        rank_started = time.perf_counter()
        result = rank(ocr_fields, visual_fields, wines, threshold=settings.match_threshold)
        rank_ms += round((time.perf_counter() - rank_started) * 1000)
        retry_ms = round((time.perf_counter() - retry_started) * 1000)

    total_ms = round((time.perf_counter() - started) * 1000)

    ranked = sorted(result.evidence.items(), key=lambda item: item[1], reverse=True)[:RESPONSE_LIMIT]
    candidates = [{"slug": slug, "score": score, "wine": wines_by_slug[slug].as_card()}
                 for slug, score in ranked if slug in wines_by_slug]
    top_score = candidates[0]["score"] if candidates else 0.0
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    margin = max(0.0, top_score - second_score)

    wine_card = (wines_by_slug[result.slug].as_card()
                if result.status == "matched" and result.slug else None)
    alternatives = [candidate["wine"] for candidate in candidates[1:4]]

    guidance = None
    if result.status == "not_found":
        guidance = "Совпадение не подтверждено. Снимите этикетку крупнее и захватите и текст, и саму бутылку."

    return {
        "status": result.status,
        "wine": wine_card,
        "candidates": candidates,
        "confidence": {"kind": "similarity", "top1Score": top_score, "margin": round(margin, 4)},
        "timing": {"totalMs": total_ms, "stages": {
            "ocr": ocr_ms, "visual": visual_ms, **({"ocrRetry": retry_ms} if retry_ms else {}),
        }},
        "alternatives": alternatives,
        "version": {
            "model": "ranking-ocr-visual-v1",
            "catalog": dataset_version,
            "configuration": f"threshold{settings.match_threshold}",
        },
        **({"guidance": guidance} if guidance else {}),
        **({"debug": {
            "preprocessing": preprocessing_debug(decoded, ocr_trace),
            "ocr": ocr_debug(ocr_trace),
            "retriever": retriever_debug(visual_candidates, visual_error, visual_ms, wines_by_slug),
            "ranking": ranking_debug(result, ocr_fields, visual_fields, wines_by_slug,
                                     settings.match_threshold, rank_ms),
        }} if settings.debug else {}),
        "isMock": False,
    }
