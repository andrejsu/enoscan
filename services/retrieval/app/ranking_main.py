"""Standalone ranking service — the one place that combines OCR field
evidence (app/ocr/main.py) and visual slug evidence (app/retriever_main.py)
into a single resolved wine, via app/ranking.py. Imports nothing from
app/service.py, app/main.py or app/index.py — the main scanner stays
untouched and unrelated.

Both producers are fetched over HTTP, concurrently, rather than loaded
in-process: each already runs as its own service, and holding a second
copy of the DINOv2 index (~1.3-2.2GB) here was enough to push the compose
stack into OOM restart loops.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .catalog import Wine, current_dataset_version, load_wines
from .common.upload import decode_upload, read_image_upload
from .label_fields import FieldCandidate, RetrievalFields, fields_from_json
from .ranking import RankingResult, rank
from .ranking_config import load_ranking_settings
from .scan_debug import (
    ocr_debug,
    ocr_search_text,
    preprocessing_debug,
    ranking_debug,
    retriever_debug,
    verification_debug,
)


# Same response contract as app/service.py and app/retriever_main.py
# (apps/web's #shared/contracts ScanResponse) — this is the one service
# meant to sit behind the product's scanner, so it must speak the same
# shape they do, not a leaner one-off.
RESPONSE_LIMIT = 5

settings = load_ranking_settings()
http_client: httpx.AsyncClient | None = None
wines_by_slug: dict[str, Wine] = {}
dataset_version = "unversioned"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global dataset_version, http_client, wines_by_slug
    dataset_version = current_dataset_version(settings.database_url)
    wines_by_slug = {wine.slug: wine for wine in load_wines(settings.database_url)}
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()
    http_client = None
    wines_by_slug = {}


app = FastAPI(title="Vinolog ranking (standalone)", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if http_client else "loading"}


async def _post_image(base_url: str, timeout: float, content: bytes, content_type: str | None,
                      filename: str | None) -> tuple[dict | None, str | None, int]:
    """(json, failure reason, ms). A slow/unreachable producer degrades the
    scan to the other one instead of failing it outright."""
    started = time.perf_counter()
    try:
        response = await http_client.post(
            f"{base_url}/v1/search",
            files={"image": (filename or "image", content, content_type or "application/octet-stream")},
            timeout=timeout,
        )
        response.raise_for_status()
        payload, error = response.json(), None
    except httpx.HTTPError as error_:
        payload, error = None, type(error_).__name__
    return payload, error, round((time.perf_counter() - started) * 1000)


@dataclass(frozen=True)
class Scan:
    result: RankingResult
    ocr: dict | None
    ocr_error: str | None
    ocr_ms: int
    ocr_fields: RetrievalFields
    visual_candidates: list[dict]
    visual_error: str | None
    visual_ms: int
    visual_fields: RetrievalFields
    rank_ms: int
    total_ms: int


async def _scan(image: UploadFile, content: bytes) -> Scan:
    """The one OCR + visual + ranking pass behind both the product and the
    evaluation route, so their top-1 can never diverge."""
    if http_client is None:
        raise HTTPException(status_code=503, detail="Ранжирование ещё загружается.")
    started = time.perf_counter()
    (ocr, ocr_error, ocr_ms), (visual, visual_error, visual_ms) = await asyncio.gather(
        _post_image(settings.ocr_base_url, settings.ocr_timeout, content, image.content_type, image.filename),
        _post_image(settings.retriever_base_url, settings.retriever_timeout, content, image.content_type,
                    image.filename),
    )
    if ocr_error and visual_error:
        raise HTTPException(status_code=503, detail="Сервисы распознавания недоступны. Повторите попытку позже.")
    ocr_fields = fields_from_json(ocr["fields"]) if ocr else RetrievalFields()
    visual_candidates = visual.get("candidates", []) if visual else []
    visual_fields = RetrievalFields(slug=tuple(FieldCandidate(c["slug"], c["score"]) for c in visual_candidates))

    rank_started = time.perf_counter()
    result = rank(ocr_fields, visual_fields, list(wines_by_slug.values()), min_margin=settings.min_margin,
                  ocr_text=ocr_search_text(ocr))
    rank_ms = round((time.perf_counter() - rank_started) * 1000)
    return Scan(result, ocr, ocr_error, ocr_ms, ocr_fields, visual_candidates, visual_error, visual_ms,
                visual_fields, rank_ms, round((time.perf_counter() - started) * 1000))


def evaluation_slug(result: RankingResult, policy: str) -> str:
    """Slug for the organizer's script; an empty string is recorded as null."""
    if result.status == "matched" and result.slug:
        return result.slug
    if policy == "top1" and result.score > 0:
        return result.ranked(1)[0][0]
    return ""


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    content = await read_image_upload(image, settings.max_upload_bytes)
    decoded = decode_upload(content)
    scan = await _scan(image, content)
    result = scan.result

    candidates = [{"slug": slug, "score": score, "wine": wines_by_slug[slug].as_card()}
                  for slug, score in result.ranked(RESPONSE_LIMIT) if slug in wines_by_slug]
    wine_card = (wines_by_slug[result.slug].as_card()
                 if result.status == "matched" and result.slug else None)
    alternatives = [candidate["wine"] for candidate in candidates[1:4]]

    guidance = None
    if result.status == "not_found":
        guidance = "Совпадение не подтверждено. Снимите этикетку крупнее и захватите и текст, и саму бутылку."

    ocr = scan.ocr
    return {
        "status": result.status,
        "wine": wine_card,
        "candidates": candidates,
        "confidence": {"kind": "similarity", "top1Score": result.score, "margin": result.margin},
        "timing": {"totalMs": scan.total_ms, "stages": {
            "ocr": scan.ocr_ms, "visual": scan.visual_ms,
        }},
        "alternatives": alternatives,
        "version": {
            "model": "ranking-ocr-visual-v3",
            "catalog": dataset_version,
            "configuration": f"margin{settings.min_margin};ocr={ocr.get('engine') if ocr else 'none'}",
        },
        **({"guidance": guidance} if guidance else {}),
        **({"debug": {
            "preprocessing": await run_in_threadpool(preprocessing_debug, decoded),
            "ocr": ocr_debug(ocr, scan.ocr_error, scan.ocr_ms, scan.ocr_fields),
            "retriever": retriever_debug(scan.visual_candidates, scan.visual_error, scan.visual_ms, wines_by_slug),
            "verification": verification_debug(result, scan.ocr_fields, wines_by_slug),
            "ranking": ranking_debug(result, scan.ocr_fields, scan.visual_fields, wines_by_slug,
                                     settings.min_margin, scan.rank_ms),
        }} if settings.debug else {}),
        "isMock": False,
    }


@app.post("/v1/eval/predict")
async def evaluation_predict(image: UploadFile = File(...)) -> dict[str, str]:
    """Strict `{"slug": "..."}` for the organizer's participant_test.sh."""
    content = await read_image_upload(image, settings.max_upload_bytes)
    decode_upload(content)  # same 4xx for a broken file as the product route
    scan = await _scan(image, content)
    return {"slug": evaluation_slug(scan.result, settings.eval_policy)}
