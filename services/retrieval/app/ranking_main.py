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

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .catalog import Wine, current_dataset_version, load_wines
from .common.upload import decode_upload, read_image_upload
from .label_fields import FieldCandidate, RetrievalFields, fields_from_json
from .ranking import rank
from .ranking_config import load_ranking_settings
from .scan_debug import ocr_debug, preprocessing_debug, ranking_debug, retriever_debug


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


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if http_client is None:
        raise HTTPException(status_code=503, detail="Ранжирование ещё загружается.")
    content = await read_image_upload(image, settings.max_upload_bytes)
    decoded = decode_upload(content)

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
    result = rank(ocr_fields, visual_fields, list(wines_by_slug.values()), threshold=settings.match_threshold)
    rank_ms = round((time.perf_counter() - rank_started) * 1000)

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
            "ocr": ocr_ms, "visual": visual_ms,
        }},
        "alternatives": alternatives,
        "version": {
            "model": "ranking-ocr-visual-v2",
            "catalog": dataset_version,
            "configuration": f"threshold{settings.match_threshold};ocr={ocr.get('engine') if ocr else 'none'}",
        },
        **({"guidance": guidance} if guidance else {}),
        **({"debug": {
            "preprocessing": await run_in_threadpool(preprocessing_debug, decoded),
            "ocr": ocr_debug(ocr, ocr_error, ocr_ms, ocr_fields),
            "retriever": retriever_debug(visual_candidates, visual_error, visual_ms, wines_by_slug),
            "ranking": ranking_debug(result, ocr_fields, visual_fields, wines_by_slug,
                                     settings.match_threshold, rank_ms),
        }} if settings.debug else {}),
        "isMock": False,
    }
