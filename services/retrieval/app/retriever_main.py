"""Standalone wine-label retriever service.

A separate process from app/main.py (the existing OCR-driven scanner): its
own FastAPI app, its own index (retriever_index.py / build_retriever_index.py),
its own settings (retriever_config.py). It exposes just enough to test the
retriever end to end — /health, /v1/search, and an image passthrough for the
UI's thumbnails — and imports nothing from app/service.py or app/ocr/.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from . import download_model
from .catalog import current_dataset_version
from .common.upload import decode_upload, read_image_upload
from .embedding import EMBEDDING_MODEL, Dinov2Encoder
from .embedding_store import EmbeddingStore
from .index_store import fetch_index, require_build
from .label_normalize import Config as LabelConfig, Segmenter
from .retriever import VisualRetriever
from .retriever_config import load_retriever_settings
from .retriever_index import RETRIEVER_INDEX_KIND, RetrieverIndex
from .storage import ObjectStore


# "candidates" in the /v1/search response holds all 10: the top pick plus 9
# ranked alternatives, sorted by score descending — see RETRIEVER.md.
RESPONSE_LIMIT = 10
ALTERNATIVES_LIMIT = RESPONSE_LIMIT - 1

settings = load_retriever_settings()
retriever: VisualRetriever | None = None
dataset_version = "unversioned"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global dataset_version, retriever
    dataset_version = current_dataset_version(settings.database_url)
    build = require_build(settings.database_url, RETRIEVER_INDEX_KIND, dataset_version)
    index = RetrieverIndex.load(str(fetch_index(ObjectStore(), build)))
    download_model.main()
    encoder = Dinov2Encoder(Path(settings.model_path), threads=4)
    embedding_store = EmbeddingStore(settings.database_url, EMBEDDING_MODEL)
    segmenter = None
    if settings.query_sam:
        segmenter = Segmenter(LabelConfig(sam_dir=Path(settings.sam_model_dir), grid=4))
    retriever = VisualRetriever(index, encoder=encoder, embedding_store=embedding_store, build_id=build.id,
                                segmenter=segmenter, use_sam=settings.query_sam,
                                visual_limit=settings.visual_limit, embedding_limit=settings.embedding_limit)
    yield
    retriever = None
    embedding_store.close()


app = FastAPI(title="Vinolog wine label retriever (standalone)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if retriever else "loading"}


def _wine_card_with_image(candidate) -> dict[str, object]:
    return candidate.wine.as_card()


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Индекс ретривера ещё загружается.")
    decoded = decode_upload(await read_image_upload(image, settings.max_upload_bytes))

    result = retriever.search(decoded, limit=RESPONSE_LIMIT)
    candidates = result.candidates
    top_score = candidates[0].score if candidates else 0.0
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    margin = max(0.0, top_score - second_score)
    top = candidates[0] if candidates else None
    wine_card = top.wine.as_card() if top else None
    alternatives = [_wine_card_with_image(item) for item in candidates[1:1 + ALTERNATIVES_LIMIT]]

    # margin=0.015 (not the original 0.04): at SIFT_WEIGHT=0.45 the 6 real
    # fixtures' correct top-1 picks had margins of 0.017-0.28, and the 2
    # genuinely wrong ones topped out at 0.011 — a real gap, not a knife's
    # edge, but calibrated on a 6-photo sample; revisit once there's a
    # bigger labelled set (see tests/tune_weights_experiment.py).
    if top and top.inliers >= 7 and top.good_matches >= 10 and top_score >= 0.3 and margin >= 0.015:
        status = "matched"
    elif top and top_score >= 0.12:
        status = "uncertain"
    else:
        status = "not_found"
    guidance = None
    if status == "uncertain":
        guidance = "Приблизьте этикетку, уберите блик и убедитесь, что название попало в кадр."
    elif status == "not_found":
        guidance = "Совпадение не подтверждено. Снимите этикетку крупнее и строго спереди."

    return {
        "status": status,
        "wine": wine_card if status == "matched" else None,
        "candidates": [
            {"slug": item.wine.slug, "score": item.score, "confidencePercent": round(item.score * 100),
             "goodMatches": item.good_matches, "inliers": item.inliers,
             "wine": _wine_card_with_image(item)}
            for item in candidates
        ],
        "confidence": {"kind": "similarity", "top1Score": top_score, "top1Percent": round(top_score * 100),
                      "margin": round(margin, 4)},
        "timing": {"totalMs": sum(result.timing.values()), "stages": result.timing},
        "alternatives": alternatives,
        "version": {"model": "retriever-sift-dinov2-v2", "catalog": dataset_version,
                    "configuration": f"standalone-retriever-sam{'on' if settings.query_sam else 'off'}"},
        **({"guidance": guidance} if guidance else {}),
        "isMock": False,
    }
