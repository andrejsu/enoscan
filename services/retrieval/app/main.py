from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from .config import load_settings
from .catalog_browser import CatalogBrowser
from .catalog import load_catalog
from .image_features import decode_image
from .index import SiftIndex
from .service import SearchService


ACCEPTED_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp"}
IMAGE_MEDIA_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
settings = load_settings()
service: SearchService | None = None
catalog_browser: CatalogBrowser | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global catalog_browser, service
    if not Path(settings.index_path).is_file():
        raise RuntimeError(f"Retrieval index is missing: {settings.index_path}")
    index = SiftIndex.load(settings.index_path)
    service = SearchService(index, catalog=load_catalog(settings.database_url)[0],
                            ocr_timeout=settings.ocr_timeout, ocr_psm=settings.ocr_psm,
                            ocr_preprocess=settings.ocr_preprocess, ocr_retry=settings.ocr_retry,
                            visual_limit=settings.visual_limit)
    catalog_browser = CatalogBrowser(settings.database_url, index)
    yield
    service = None
    catalog_browser = None


app = FastAPI(title="Vinolog retrieval", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if service else "loading"}


@app.get("/v1/wines/{slug}/image", response_class=FileResponse)
def wine_image(slug: str) -> FileResponse:
    if service is None:
        raise HTTPException(status_code=503, detail="Индекс поиска ещё загружается.")

    reference = next((item for item in service.index.references if item.wine.slug == slug), None)
    if reference is None:
        raise HTTPException(status_code=404, detail="Изображение вина не найдено.")

    uploads = (Path(settings.dataset_root) / "uploads").resolve()
    image_path = (uploads / reference.relative_path).resolve()
    media_type = IMAGE_MEDIA_TYPES.get(image_path.suffix.casefold())
    if not image_path.is_relative_to(uploads) or not image_path.is_file() or not media_type:
        raise HTTPException(status_code=404, detail="Изображение вина не найдено.")

    return FileResponse(
        image_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/v1/catalog")
def catalog(
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=60),
    image_status: str = Query(default="all", pattern="^(all|indexed|missing)$"),
) -> dict[str, object]:
    if catalog_browser is None:
        raise HTTPException(status_code=503, detail="Каталог ещё загружается.")
    return catalog_browser.browse(
        query=q,
        page=page,
        per_page=per_page,
        image_status=image_status,
    )


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
