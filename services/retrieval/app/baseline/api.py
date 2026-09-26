from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile

from ..catalog.repository import current_dataset_version
from ..common.upload import decode_upload, read_image_upload
from ..index_store import fetch_index, require_build
from ..sift_index import SiftIndex
from ..storage import ObjectStore
from .config import SIFT_CONFIG, SIFT_INDEX_KIND, load_settings
from .service import BaselineSearch


settings = load_settings()
service: BaselineSearch | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global service
    version = current_dataset_version(settings.database_url)
    build = require_build(settings.database_url, SIFT_INDEX_KIND, version)
    index = SiftIndex.load(str(fetch_index(ObjectStore(), build)), SIFT_CONFIG)
    service = BaselineSearch(index, visual_limit=settings.visual_limit, dataset_version=version)
    yield
    service = None


app = FastAPI(title="Vinolog retrieval", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if service else "loading"}


@app.post("/v1/search")
async def product_search(image: UploadFile = File(...)) -> dict[str, object]:
    content = await read_image_upload(image, settings.max_upload_bytes)
    if service is None:
        raise HTTPException(status_code=503, detail="Индекс поиска ещё загружается.")
    return service.search(decode_upload(content)).body
