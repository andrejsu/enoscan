# Retrieval service

Локальный baseline поиска конкретной карточки по фотографии этикетки. Он строит SIFT-индекс по фото, привязанным к винам в таблице `wine_images` (её заполняет `services/importer`), получает кандидатов через FLANN и перепроверяет их геометрию через RANSAC — чисто визуальный поиск. Сервис не зависит от Nuxt UI и не использует облачные ключи.

OCR (RapidOCR) и объединение его результата с визуальным поиском больше не часть этого сервиса — они вынесены в отдельные сервисы: `ocr-retriever` (`app/ocr/main.py`) отдаёт per-поле кандидатов, `ranking` (`app/ranking_main.py`) комбинирует их с визуальными кандидатами `retriever` и резолвит slug. `ranking` — тот сервис, что реально стоит за продуктовым сканером (`apps/web`'s `/api/scans`, через `NUXT_RANKING_BASE_URL`); он же отдаёт оценочный `/v1/eval/predict` на порту 8080, чтобы top-1 оценки и сканера совпадал. `retrieval` (этот сервис, порт 8084) остаётся визуальным baseline для `scripts/eval_search.py`. См. `app/label_fields.py` и `app/ranking.py`.

Swagger `ranking` — `http://127.0.0.1:8080/docs` (OpenAPI JSON — `/openapi.json`): оба маршрута, поле `image`, схемы ответов и ошибок. Схемы — `app/ranking_schemas.py`, они повторяют `ScanResponse` из `apps/web/shared/contracts`.

Когда `ranking` не подтверждает совпадение, ответ `/v1/search` содержит `recommendations` — вина каталога той же винодельни, линейки (редкое слово названия на этикетке) или сорта вместе с ещё одним параметром, с причиной и расхождением с этикеткой (`app/recommendations.py`). На решение и score ранжирования они не влияют.

Фото с известным ответом лежат в `tests/fixtures`: `green/` — вино есть в каталоге (имя файла — slug), `red/` — вина нет, `yellow/` — вина нет, но есть его винодельня или линейка. `tests/test_fixture_photos.py` прогоняет их через маршрут `ranking` этого рабочего дерева с живыми `ocr-retriever`, `retriever` и БД (без них тесты пропускаются): green должны совпасть, red — дать `not_found`, yellow — `not_found` с рекомендацией нужной винодельни.

## Запуск

Корневой `docker compose up --build` сначала запускает `importer`, затем `retrieval-index`, затем поднимает API:

- `POST /v1/search` — ответ `matched | uncertain | not_found` визуального baseline;
- `GET /health` — готовность загруженного индекса.

Каталог для админки и картинки вин отдаёт Nuxt напрямую из PostgreSQL и MinIO, этот сервис их не проксирует.

## Хранилища

- Каталог и привязка фото читаются из PostgreSQL (`wines`, `wine_images`, `images`). Версия данных — последний успешный `import_runs.dataset_version`; она же возвращается в `version.catalog`.
- `retrieval-index` скачивает эталонные картинки из бакета `vinolog-images` и сохраняет индекс в `vinolog-indexes/sift-v3/<version>.npz`. Сборка регистрируется в `index_builds` и `index_references`. Для уже собранной версии индексатор сразу завершается.
- `retriever-index` сохраняет свою SIFT-часть в `vinolog-indexes/retriever-v2/<version>.npz`, а эмбеддинги DINOv2 пишет в `image_embeddings` (pgvector). Ключ эмбеддинга — sha256 картинки и строка модели `EMBEDDING_MODEL` (`app/embedding.py`), поэтому считаются только новые картинки. При смене модели или параметров нормализации эталонов меняйте эту строку.
- При старте сервисы скачивают индекс текущей версии в `/tmp/vinolog-indexes`. Если индекса для текущей версии нет, старт завершается ошибкой.

Изменили данные или `db/image-overrides.csv` — выполните `docker compose up -d`: importer создаст новую версию, индексаторы соберут индексы под неё. Удалять тома не нужно.

SIFT — измеримый baseline, а не заявленная финальная точность. Визуальные embeddings (DINOv2) и OCR-переранжирование уже реализованы, но как отдельные сервисы (`retriever`, `ocr-retriever`, `ranking`) рядом с этим, а не изменения внутри `SearchService` — см. `services/retrieval/app/retriever.py`, `app/ocr/retriever.py`, `app/ranking.py`.
