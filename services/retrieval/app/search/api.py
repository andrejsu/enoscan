"""Ranking service (compose service `ranking`): upload checks, the product
and evaluation routes and the product response. The scan itself — OCR and
the visual retriever combined into one resolved wine — is search/service.py.
"""

from contextlib import asynccontextmanager

import httpx
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..catalog.repository import current_dataset_version, load_wines
from ..common.upload import decode_upload, read_image_upload
from .config import load_search_settings
from .debug import ocr_debug, preprocessing_debug, ranking_debug, retriever_debug, verification_debug
from .schemas import UPLOAD_ERRORS, EvaluationPrediction, HealthResponse, ScanResponse
from .service import ProducersUnavailable, Scan, SearchService, evaluation_slug


RESPONSE_LIMIT = 5
NOT_FOUND_GUIDANCE = "Совпадение не подтверждено. Снимите этикетку крупнее и захватите и текст, и саму бутылку."

settings = load_search_settings()
service: SearchService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global service
    dataset_version = current_dataset_version(settings.database_url)
    wines = load_wines(settings.database_url)
    async with httpx.AsyncClient() as client:
        service = SearchService(settings, wines, dataset_version, client)
        yield
        service = None


EVAL_POLICY_ANSWERS = {
    "matched": "пустой `slug` (скрипт запишет `null`), когда совпадение не подтверждено",
    "top1": "лучшее вино всегда, даже когда совпадение не подтверждено",
}

API_DESCRIPTION = f"""
Сканер винных этикеток: по фотографии находит карточку вина в каталоге.

## Проверка скриптом кейсодержателя

Скрипт `participant_test.sh` (лежит в `data/eval/`, там же `README.md`)
отправляет фото по одному на `POST /v1/eval/predict` и записывает ответы
в `predictions.jsonl`, который передаётся организатору.

| Где запущен сканер | `--endpoint` |
|---|---|
| локально, `docker compose up` | `http://127.0.0.1:8080/v1/eval/predict` (адрес по умолчанию в скрипте) |
| на сайте | `https://<домен сайта>/v1/eval/predict` |

```bash
cd data/eval
./participant_test.sh \\
  --images-dir ./queries \\
  --manifest ./queries.tsv \\
  --endpoint 'http://127.0.0.1:8080/v1/eval/predict' \\
  --output ./predictions.jsonl
```

Одно фото вручную — то же, что делает скрипт:

```bash
curl -F 'image=@queries/019c68d0.jpg' http://127.0.0.1:8080/v1/eval/predict
# {{"slug":"<slug вина из каталога>"}}
```

Что скрипт ждёт и что отдаёт сервис:

- запрос — `multipart/form-data`, фото в поле `image` (JPEG, PNG или WebP, до 10 МБ);
- ответ — HTTP 200 и плоский JSON `{{"slug": "..."}}` со slug вина из каталога;
- при любом другом коде, пустом `slug` или ответе дольше 10 секунд скрипт
  записывает `predicted_slug: null`;
- неуверенный ответ зависит от `RANKING_EVAL_POLICY`, сейчас
  `{settings.eval_policy}`: {EVAL_POLICY_ANSWERS[settings.eval_policy]}.

## Маршруты

Оба маршрута делают один и тот же проход — OCR и визуальный ретривер
параллельно, затем ранжирование с проверкой по этикетке, — поэтому top-1
у них всегда совпадает.

- `POST /v1/eval/predict` — для скрипта кейсодержателя: плоский `{{"slug": "..."}}`.
- `POST /v1/search` — для продуктового сканера: статус, карточка, top-5,
  отрыв top-1 от top-2, рекомендации, когда вино не найдено.
"""

app = FastAPI(title="Vinolog ranking", version="0.3.0", lifespan=lifespan, description=API_DESCRIPTION,
              openapi_tags=[{"name": "scan", "description": "Поиск вина по фото этикетки."},
                            {"name": "service", "description": "Состояние сервиса."}])

IMAGE_FIELD = File(..., description="Фото этикетки: JPEG, PNG или WebP, до 10 МБ.")


@app.get("/health", tags=["service"], response_model=HealthResponse, summary="Готовность сервиса")
def health() -> dict[str, str]:
    return {"status": "ok" if service else "loading"}


async def _scan(image: UploadFile) -> tuple[np.ndarray, Scan]:
    """The checked, decoded upload and its scan; a bad file fails before an outage does."""
    content = await read_image_upload(image, settings.max_upload_bytes)
    decoded = decode_upload(content)
    if service is None:
        raise HTTPException(status_code=503, detail="Ранжирование ещё загружается.")
    try:
        return decoded, await service.scan(content, image.content_type, image.filename)
    except ProducersUnavailable:
        raise HTTPException(status_code=503,
                            detail="Сервисы распознавания недоступны. Повторите попытку позже.") from None


@app.post("/v1/search", tags=["scan"], response_model=ScanResponse, response_model_exclude_unset=True,
          responses=UPLOAD_ERRORS, summary="Найти вино по фото (продуктовый ответ)")
async def search(image: UploadFile = IMAGE_FIELD) -> dict[str, object]:
    """`matched` — вино найдено и в `wine` его карточка. `not_found` — уверенного
    ответа нет: `candidates` показывают лучших по score, `recommendations` —
    вина той же винодельни или линейки, если этикетка на них указывает."""
    decoded, scan = await _scan(image)
    result, wines = scan.result, service.wines_by_slug

    candidates = [{"slug": slug, "score": score, "wine": wines[slug].as_card()}
                  for slug, score in result.ranked(RESPONSE_LIMIT) if slug in wines]
    recommendations = [
        {"slug": item.slug, "score": item.score, "wine": wines[item.slug].as_card(),
         "sharedFields": list(item.shared_fields), "reason": item.reason, "difference": item.difference}
        for item in service.recommend(scan)
    ]
    ocr = scan.ocr.payload
    return {
        "status": result.status,
        "wine": wines[result.slug].as_card() if result.status == "matched" and result.slug else None,
        "candidates": candidates,
        "confidence": {"kind": "similarity", "top1Score": result.score, "margin": result.margin},
        "timing": {"totalMs": scan.total_ms, "stages": {"ocr": scan.ocr.ms, "visual": scan.visual.ms}},
        "alternatives": [candidate["wine"] for candidate in candidates[1:4]],
        "recommendations": recommendations,
        "version": {
            "model": "ranking-ocr-visual-v3",
            "catalog": service.dataset_version,
            "configuration": f"margin{settings.min_margin};ocr={ocr.get('engine') if ocr else 'none'}",
        },
        **({"guidance": NOT_FOUND_GUIDANCE} if result.status == "not_found" else {}),
        **({"debug": {
            "preprocessing": await run_in_threadpool(preprocessing_debug, decoded),
            "ocr": ocr_debug(scan.ocr, scan.ocr_fields),
            "retriever": retriever_debug(scan.visual, scan.visual_candidates, wines),
            "verification": verification_debug(result, scan.ocr_fields, wines),
            "ranking": ranking_debug(result, scan.ocr_fields, scan.visual_fields, wines,
                                     settings.min_margin, scan.rank_ms),
        }} if settings.debug else {}),
        "isMock": False,
    }


@app.post("/v1/eval/predict", tags=["scan"], response_model=EvaluationPrediction, responses=UPLOAD_ERRORS,
          summary="Top-1 slug для скрипта кейсодержателя (participant_test.sh)")
async def evaluation_predict(image: UploadFile = IMAGE_FIELD) -> dict[str, str]:
    """Маршрут для `participant_test.sh` кейсодержателя: плоский `{"slug": "..."}`
    с top-1 вином каталога. Как запустить скрипт — в описании API вверху страницы.

    При `RANKING_EVAL_POLICY=matched` (по умолчанию) неуверенный ответ — пустая
    строка, скрипт записывает её как `null`; при `top1` всегда отдаётся лучшее
    вино. Скрипт ждёт ответ не дольше 10 секунд."""
    _, scan = await _scan(image)
    return {"slug": evaluation_slug(scan.result, settings.eval_policy)}
