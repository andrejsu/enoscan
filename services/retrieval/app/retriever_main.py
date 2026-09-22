"""Standalone wine-label retriever service.

A separate process from app/main.py (the existing OCR-driven scanner): its
own FastAPI app, its own index (retriever_index.py / build_retriever_index.py),
its own settings (retriever_config.py). It exposes just enough to test the
retriever end to end — /health, /v1/search, and an image passthrough for the
UI's thumbnails — and imports nothing from app/service.py or app/ocr.py.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import download_model
from .embedding import Dinov2Encoder
from .image_features import decode_image
from .label_normalize import Config as LabelConfig, Segmenter
from .retriever import VisualRetriever
from .retriever_config import load_retriever_settings
from .retriever_index import RetrieverIndex


ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}
IMAGE_MEDIA_TYPES = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
# "candidates" in the /v1/search response holds all 10: the top pick plus 9
# ranked alternatives, sorted by score descending — see RETRIEVER.md.
RESPONSE_LIMIT = 10
ALTERNATIVES_LIMIT = RESPONSE_LIMIT - 1

settings = load_retriever_settings()
retriever: VisualRetriever | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global retriever
    if not Path(settings.index_path).is_file():
        raise RuntimeError(f"Retriever index is missing: {settings.index_path}")
    index = RetrieverIndex.load(settings.index_path)
    encoder = None
    segmenter = None
    if index.embeddings is not None:
        download_model.main()
        encoder = Dinov2Encoder(Path(settings.model_path), threads=4)
        if settings.query_sam:
            segmenter = Segmenter(LabelConfig(sam_dir=Path(settings.sam_model_dir), grid=4))
    retriever = VisualRetriever(index, encoder=encoder, segmenter=segmenter, use_sam=settings.query_sam,
                                visual_limit=settings.visual_limit, embedding_limit=settings.embedding_limit)
    yield
    retriever = None


app = FastAPI(title="Vinolog wine label retriever (standalone)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if retriever else "loading"}


@app.get("/v1/wines/{slug}/image", response_class=FileResponse)
def wine_image(slug: str) -> FileResponse:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Индекс ретривера ещё загружается.")
    reference = retriever._reference_by_slug.get(slug)
    if reference is None:
        raise HTTPException(status_code=404, detail="Изображение вина не найдено.")
    uploads = (Path(settings.dataset_root) / "uploads").resolve()
    image_path = (uploads / reference.relative_path).resolve()
    media_type = IMAGE_MEDIA_TYPES.get(image_path.suffix.casefold())
    if not image_path.is_relative_to(uploads) or not image_path.is_file() or not media_type:
        raise HTTPException(status_code=404, detail="Изображение вина не найдено.")
    return FileResponse(image_path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})


def _wine_card_with_image(candidate) -> dict[str, object]:
    card = candidate.wine.as_card()
    card["imageUrl"] = f"/v1/wines/{quote(candidate.wine.slug, safe='')}/image" if candidate.relative_path else None
    return card


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Индекс ретривера ещё загружается.")
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

    result = retriever.search(decoded, limit=RESPONSE_LIMIT)
    candidates = result.candidates
    top_score = candidates[0].score if candidates else 0.0
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    margin = max(0.0, top_score - second_score)
    top = candidates[0] if candidates else None
    wine_card = top.wine.as_card() if top else None
    if wine_card:
        wine_card["imageUrl"] = f"/v1/wines/{quote(top.wine.slug, safe='')}/image"
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
             "wine": _wine_card_with_image(item)}
            for item in candidates
        ],
        "confidence": {"kind": "similarity", "top1Score": top_score, "top1Percent": round(top_score * 100),
                      "margin": round(margin, 4)},
        "timing": {"totalMs": sum(result.timing.values()), "stages": result.timing},
        "alternatives": alternatives,
        "version": {"model": "retriever-sift-dinov2-v1", "catalog": "dataset-v1",
                    "configuration": f"standalone-retriever-sam{'on' if settings.query_sam else 'off'}"},
        **({"guidance": guidance} if guidance else {}),
        "isMock": False,
    }
