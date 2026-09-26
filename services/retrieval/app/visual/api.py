"""Visual retriever service (compose service `retriever`): /health and
/v1/search over its SIFT + DINOv2 index. The ranking service (app/search)
reads only the candidates of the /v1/search response.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from ..catalog.repository import current_dataset_version
from ..common.upload import decode_upload, read_image_upload
from ..index_store import fetch_index, require_build
from ..sift_index import SiftIndex
from ..storage import ObjectStore
from . import download_model
from .config import RETRIEVER_INDEX_KIND, SIFT_CONFIG, load_retriever_settings
from .embedding import EMBEDDING_MODEL, Dinov2Encoder
from .embedding_store import EmbeddingStore
from .preprocessing import Config as LabelConfig, Segmenter
from .retriever import VisualRetriever


RESPONSE_LIMIT = 10
GUIDANCE = {
    "uncertain": "Приблизьте этикетку, уберите блик и убедитесь, что название попало в кадр.",
    "not_found": "Совпадение не подтверждено. Снимите этикетку крупнее и строго спереди.",
}

settings = load_retriever_settings()
retriever: VisualRetriever | None = None
dataset_version = "unversioned"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global dataset_version, retriever
    dataset_version = current_dataset_version(settings.database_url)
    build = require_build(settings.database_url, RETRIEVER_INDEX_KIND, dataset_version)
    index = SiftIndex.load(str(fetch_index(ObjectStore(), build)), SIFT_CONFIG)
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


@app.post("/v1/search")
async def search(image: UploadFile = File(...)) -> dict[str, object]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Индекс ретривера ещё загружается.")
    decoded = decode_upload(await read_image_upload(image, settings.max_upload_bytes))

    result = retriever.search(decoded, limit=RESPONSE_LIMIT)
    candidates = result.candidates
    top = candidates[0] if candidates else None
    top_score = top.score if top else 0.0
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    margin = max(0.0, top_score - second_score)

    if top and top.inliers >= 7 and top.good_matches >= 10 and top_score >= 0.3 and margin >= 0.015:
        status = "matched"
    elif top and top_score >= 0.12:
        status = "uncertain"
    else:
        status = "not_found"
    guidance = GUIDANCE.get(status)

    return {
        "status": status,
        "wine": top.wine.as_card() if status == "matched" else None,
        "candidates": [
            {"slug": item.wine.slug, "score": item.score, "confidencePercent": round(item.score * 100),
             "goodMatches": item.good_matches, "inliers": item.inliers, "wine": item.wine.as_card()}
            for item in candidates
        ],
        "confidence": {"kind": "similarity", "top1Score": top_score, "top1Percent": round(top_score * 100),
                       "margin": round(margin, 4)},
        "timing": {"totalMs": sum(result.timing.values()), "stages": result.timing},
        "alternatives": [item.wine.as_card() for item in candidates[1:RESPONSE_LIMIT]],
        "version": {"model": "retriever-sift-dinov2-v2", "catalog": dataset_version,
                    "configuration": f"standalone-retriever-sam{'on' if settings.query_sam else 'off'}"},
        **({"guidance": guidance} if guidance else {}),
        "isMock": False,
    }
