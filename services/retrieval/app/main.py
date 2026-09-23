from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, File, HTTPException, UploadFile

from .catalog import current_dataset_version
from .config import load_settings
from .image_features import decode_image
from .index import SIFT_INDEX_KIND, SiftIndex
from .index_store import fetch_index, require_build
from .service import SearchService
from .storage import ObjectStore


ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}
settings = load_settings()
service: SearchService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global service
    version = current_dataset_version(settings.database_url)
    build = require_build(settings.database_url, SIFT_INDEX_KIND, version)
    index = SiftIndex.load(str(fetch_index(ObjectStore(), build)))
    service = SearchService(index, visual_limit=settings.visual_limit, dataset_version=version)
    yield
    service = None


app = FastAPI(title="Vinolog retrieval", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if service else "loading"}


async def read_image_upload(image: UploadFile) -> bytes:
    if image.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="Поддерживаются JPEG, PNG и WebP.")
    content = await image.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Добавьте фотографию в поле image.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Размер фотографии не должен превышать 10 МБ.")
    return content


def run_search(content: bytes) -> dict[str, object]:
    if service is None:
        raise HTTPException(status_code=503, detail="Индекс поиска ещё загружается.")
    try:
        image = decode_image(content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return service.search(image).body


@app.post("/v1/search")
async def product_search(image: UploadFile = File(...)) -> dict[str, object]:
    return run_search(await read_image_upload(image))


@app.post("/v1/eval/predict")
async def evaluation_search(image: UploadFile = File(...)) -> dict[str, str]:
    started = perf_counter()
    result = run_search(await read_image_upload(image))
    candidates = result["candidates"]
    top = candidates[0] if isinstance(candidates, list) and candidates else None
    slug = top.get("slug") if isinstance(top, dict) else None
    _ = perf_counter() - started
    return {"slug": slug if isinstance(slug, str) else ""}
