# Импорт каталога и изображений в Postgres + MinIO

Дата: 2026-09-22. Статус: реализовано в ветке `plan-postgres-minio-dataset-import`; открыты ручные проверки, отмеченные ниже.

## Overview

Заменить цепочку `dataset-init → db-import → volume dataset` одним идемпотентным сервисом `importer`. Состояние остаётся в двух хранилищах:

- **PostgreSQL (с pgvector)** хранит типизированный каталог, явную привязку фото к винам, ручные исправления, журнал проблем импорта, версии датасета, описания собранных индексов и эмбеддинги DINOv2.
- **MinIO** хранит оригиналы изображений (ключ — sha256), сгенерированные превью, SIFT-индексы и проверочные наборы.

Все потребители переводятся на эти хранилища: индексаторы, `retrieval`, `retriever`, Nuxt (картинки, админка, сомелье) и скрипты оценки. Привязка фото больше не вычисляется при сборке индекса, а картинка вина отдаётся независимо от индекса.

## Current State Analysis

- `scripts/init-dataset.sh` распаковывает RAR в volume `dataset`, строит `uploads.csv` через `scripts/build-media-manifest.py` и ставит маркер `.ready`. Недособранный `current` требует удалить volume вручную (`scripts/init-dataset.sh:46-49`).
- `db/import-dataset.sh:9-19`: если CSV изменился, импорт падает и требует новую БД. `db/import-dataset.sql` загружает CSV в `text`-колонки `wine_catalog_raw`. View `wine_catalog` молча схлопывает дубли slug через `DISTINCT ON`. `wine_media` — просто список файлов без связи с винами.
- Привязка фото — эвристика `resolve_references` (`services/retrieval/app/catalog.py:134-195`). Её заново вызывают `build_index.py:17` и `build_retriever_index.py:36`, а результат живёт только внутри `.npz`.
- Индексы пропускают пересборку по одному признаку `output.exists()` (`build_index.py:12`, `build_retriever_index.py:27`), поэтому после смены данных остаются старыми.
- Картинку вина отдаёт retrieval по ссылке из индекса (`services/retrieval/app/main.py:52-70`, `retriever_main.py:62-73`). Если SIFT отбросил эталон (меньше 8 дескрипторов, `build_index.py:30`), будет 404, хотя файл есть.
- Сомелье ставит `imageUrl`, если в CSV заполнено имя фото (`apps/web/server/utils/sommelier-catalog.ts:53`), даже когда картинки нет.
- Админка ходит через Nuxt в retrieval `/v1/catalog` (`apps/web/server/api/admin/wines.get.ts:15`, `services/retrieval/app/catalog_browser.py`), а признак «в индексе» берётся из загруженного `.npz`.
- Версия каталога в ответе поиска захардкожена: `"catalog": "dataset-v1"` (`services/retrieval/app/service.py:139`).
- Эмбеддинги DINOv2 хранятся в `retriever-v1.npz`, похожесть считается точным косинусом со всеми эталонами в памяти (`retriever_index.py:106-112`, `retriever.py:73-78`). При каждой сборке индекса эмбеддинги считаются заново для всех эталонов.
- Аудит `reports/mapping_audit_2026-09-16.json`: 2098 привязок, 182 подозрительные, 4113 оригиналов без вина, 183 предложенных исправления.
- Архив: RAR5, три тома, **не solid** (проверено `7zz l -slt`). 15 807 файлов, из них 6 202 оригинала `jpg/jpeg/png/webp`. Остальное — копии Strapi `thumbnail_/small_/medium_/large_`, `.geojson`, `.xml`, `.tif`.
- Есть `data/dataset/Реальные фото.zip` (200 записей, включая `__MACOSX`), пайплайн его не использует.
- Локально доступен образ `quay.io/minio/minio:RELEASE.2025-03-12T18-04-18Z`. Community-версия MinIO больше не публикует новые образы, поэтому тег фиксируется, а код пишется под любой S3.

## Desired End State

```text
data/dataset (ro) ─► importer ─┬─► Postgres: wines, images, wine_images, import_runs, …
db/migrations, db/image-overrides.csv ┘   └─► MinIO: vinolog-images, vinolog-eval
                                   │
          ┌────────────────────────┴───────────────────────┐
   retrieval-index                                  retriever-index
   SIFT → MinIO vinolog-indexes/sift-v3/{ver}.npz   DINOv2 → image_embeddings (pgvector)
   index_builds / index_references                  SIFT → vinolog-indexes/retriever-v2/{ver}.npz
          │                                                │
      retrieval ───────────────► web ◄──────────────── retriever
                    Nuxt: /api/wines/{slug}/image?size=… читает Postgres и MinIO,
                    /api/admin/wines — SQL, сомелье — SQL по wines
```

Как проверить результат:

1. На чистых volumes `docker compose up --build -d` поднимает стек без ручных шагов. `import_runs` содержит одну успешную запись, в `wines` около 6 000 строк, `images` = 6 202 или меньше (дубли по содержимому схлопнуты), для каждого `images` в MinIO есть оригинал и превью.
2. Повторный `docker compose up` с теми же данными: importer и оба индексатора выходят без работы.
3. Если изменить только `db/image-overrides.csv`, появляется новая версия: импорт проходит без чтения RAR, SIFT-индексы пересобираются, эмбеддинги пересчитываются только для новых изображений.
4. Картинка отдаётся для любого вина с привязкой, даже если его нет в SIFT-индексе.
5. В репозитории нет `Dockerfile.dataset`, `scripts/init-dataset.sh`, `scripts/build-media-manifest.py`, `db/import-dataset.*`, `services/retrieval/app/catalog_browser.py`, а в compose нет volumes `dataset`, `retrieval-index` и `retriever-index-data`.

## What We're NOT Doing

- UI для проверки подозрительных привязок и правки overrides из админки. Исправления вносятся только через `db/image-overrides.csv`.
- Изменение алгоритмов поиска, весов (`SIFT_WEIGHT`/`EMBEDDING_WEIGHT`), порогов статусов, OCR.
- Перенос SIFT-дескрипторов в Postgres: они остаются файлом `.npz` в MinIO.
- ANN-индекс (HNSW/IVFFlat) по эмбеддингам. Около 2 000 векторов по 384 измерения — точный поиск занимает миллисекунды и совпадает с текущим поведением.
- Несколько фото на одно вино в UI. Схема допускает это (`is_primary`), но импорт выбирает ровно одно основное.
- Публичный доступ к MinIO и presigned-ссылки. Картинки проксируются через Nuxt.
- Замену MinIO на другой S3 и продакшен-развёртывание.
- Сохранение совместимых view `wine_catalog`/`wine_media` и старых таблиц.
- Изменения `scripts/smoke_search.py`: он проверяет HTTP и читает локальный `eval.zip`.

## Implementation Approach

- **Один сквозной переход.** Первая миграция удаляет старые таблицы. Между этапами 1 и 5 стек в ветке не работает целиком, каждый этап проверяется своими тестами. Сливать ветку в `master` можно только после этапа 6.
- **Адресация по содержимому.** Объекты картинок и эмбеддинги адресуются sha256 изображения. Повторная загрузка и повторный расчёт пропускаются по наличию объекта или строки.
- **Версия датасета.** `dataset_version` — sha256 от хэшей CSV, трёх томов RAR, `db/image-overrides.csv` и констант `MAPPING_ALGO_VERSION` и `PREVIEW_VERSION`. Индексы и их записи в `index_builds` привязаны к этой версии.
- **Схема через миграции.** Файлы `db/migrations/NNN_name.sql` применяет importer под advisory lock. Каждый файл выполняется в отдельной транзакции, в `schema_migrations` пишутся имя и sha256. Если уже применённый файл изменился, запуск останавливается.
- **Граница транзакции.** Загрузки в MinIO и строки `images` идемпотентны и пишутся по ходу работы. Каталог, привязка, overrides, issues и отметка об успехе run пишутся одной транзакцией в конце.
- **Эвристика переезжает, а не копируется.** Функции привязки из `services/retrieval/app/catalog.py` переносятся в `services/importer` и удаляются из retrieval.
- **S3-клиент.** В Python — `boto3`, в Nuxt — `@aws-sdk/client-s3`. Endpoint и ключи задаются через окружение, привязки к MinIO в коде нет.

---

## Phase 1: Инфраструктура и схема

### Overview
Postgres с pgvector, MinIO, каркас `services/importer` с запуском миграций, полная схема.

### Changes Required

#### 1. `compose.yaml`
- `db.image`: `pgvector/pgvector:0.8.0-pg16`. Мажорная версия PG та же, существующий `postgres-data` подходит.
- Новый сервис `minio`: `quay.io/minio/minio:RELEASE.2025-03-12T18-04-18Z`, `command: ["server", "/data", "--console-address", ":9001"]`, `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` из `.env` со значениями по умолчанию `vinolog`/`vinolog-secret`, порты `127.0.0.1:${VINLOG_S3_PORT:-9000}:9000` и `127.0.0.1:${VINLOG_S3_CONSOLE_PORT:-9001}:9001`, volume `minio-data`, healthcheck `["CMD", "mc", "ready", "local"]`.
- Новый сервис `importer`: `build: ./services/importer`, `depends_on` на `db` (healthy) и `minio` (healthy), volumes `./data/dataset:/input:ro` и `./db:/db:ro`, окружение `PG*`, `S3_ENDPOINT=http://minio:9000`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION=us-east-1`, `restart: "no"`.
- Общий YAML-якорь `x-storage-environment` для S3-переменных, чтобы переиспользовать его в этапах 3–5.
- Удалить сервисы `dataset-init` и `db-import`, а из `depends_on` остальных сервисов — ссылки на них. Иначе `db-import` снова создаст `wine_catalog_raw` после миграции `001`. Файлы старого пайплайна удаляются на этапе 6.

#### 2. `services/importer/`
```
services/importer/
  Dockerfile
  requirements.txt
  importer/__init__.py
  importer/__main__.py
  importer/config.py
  importer/db.py
  importer/migrations.py
  importer/storage.py
  tests/test_migrations.py
```
- `Dockerfile`: `python:3.12-slim-bookworm`. Включает non-free компоненты, как `Dockerfile.dataset:3-6`, и ставит `unrar`, затем `pip install -r requirements.txt`. `CMD ["python", "-m", "importer"]`.
- `requirements.txt`: `psycopg[binary]==3.2.10`, `boto3==1.40.*`, `rarfile==4.2`, `Pillow==11.3.*`, `pytest==8.3.*`.
- `config.py`: dataclass `Settings` (DB URL собирается из `PG*` так же, как в `services/retrieval/app/config.py:18-26`, плюс S3 и пути `/input` и `/db`).
- `migrations.py`: `apply_migrations(connection, directory)`. Берёт `pg_advisory_lock(hashtext('vinolog-migrations'))`, создаёт `schema_migrations(filename text PK, sha256 text, applied_at timestamptz)`, применяет файлы по порядку имён, каждый в своей транзакции. Если sha256 уже применённого файла отличается, падает с `SystemExit`.
- `storage.py`: `ObjectStore` поверх boto3 с методами `ensure_bucket`, `exists`, `put_bytes`, `put_file`, `get_bytes`, `download_file`.
- На этом этапе `__main__.py` только применяет миграции и создаёт бакеты `vinolog-images`, `vinolog-indexes`, `vinolog-eval`.

#### 3. `db/migrations/001_catalog_schema.sql`
```sql
DROP VIEW IF EXISTS wine_catalog;
DROP TABLE IF EXISTS wine_catalog_raw, wine_media, dataset_imports;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE import_runs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dataset_version text NOT NULL,
  catalog_sha256 text NOT NULL,
  archive_sha256 text NOT NULL,
  overrides_sha256 text NOT NULL,
  mapping_algo_version text NOT NULL,
  preview_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
  stats jsonb NOT NULL DEFAULT '{}',
  error text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE UNIQUE INDEX import_runs_succeeded_version_idx ON import_runs (dataset_version) WHERE status = 'succeeded';

CREATE TABLE catalog_rows_raw (
  run_id bigint NOT NULL REFERENCES import_runs (id) ON DELETE CASCADE,
  row_no integer NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY (run_id, row_no)
);

CREATE TABLE wines (
  slug text PRIMARY KEY,
  name text,
  category text,
  color text,
  region text,
  grape_varieties text[] NOT NULL DEFAULT '{}',
  description text,
  winery text,
  source_image_filename text,
  source_row_no integer NOT NULL,
  raw_record_count integer NOT NULL,
  is_active boolean NOT NULL,
  first_seen_run_id bigint NOT NULL REFERENCES import_runs (id),
  updated_run_id bigint NOT NULL REFERENCES import_runs (id)
);

CREATE TABLE images (
  sha256 text PRIMARY KEY,
  object_key text NOT NULL UNIQUE,
  preview_key text NOT NULL UNIQUE,
  mime text NOT NULL,
  width integer NOT NULL,
  height integer NOT NULL,
  size_bytes bigint NOT NULL,
  preview_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE image_sources (
  strapi_path text PRIMARY KEY,
  filename text NOT NULL,
  image_sha256 text NOT NULL REFERENCES images (sha256),
  archive_sha256 text NOT NULL
);
CREATE INDEX image_sources_sha_idx ON image_sources (image_sha256);

CREATE TABLE wine_images (
  slug text NOT NULL REFERENCES wines (slug),
  image_sha256 text NOT NULL REFERENCES images (sha256),
  strapi_path text NOT NULL REFERENCES image_sources (strapi_path),
  is_primary boolean NOT NULL,
  mapping_kind text NOT NULL CHECK (mapping_kind IN ('image_filename', 'slug', 'fuzzy_filename', 'manual')),
  mapping_score real NOT NULL,
  review_status text NOT NULL CHECK (review_status IN ('auto', 'suspicious', 'confirmed')),
  run_id bigint NOT NULL REFERENCES import_runs (id),
  PRIMARY KEY (slug, image_sha256)
);
CREATE UNIQUE INDEX wine_images_primary_idx ON wine_images (slug) WHERE is_primary;
CREATE INDEX wine_images_sha_idx ON wine_images (image_sha256);

CREATE TABLE image_overrides (
  line_no integer PRIMARY KEY,
  slug text NOT NULL,
  action text NOT NULL CHECK (action IN ('set', 'reject', 'confirm')),
  strapi_filename text,
  note text,
  run_id bigint NOT NULL REFERENCES import_runs (id)
);

CREATE TABLE import_issues (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES import_runs (id) ON DELETE CASCADE,
  kind text NOT NULL,
  slug text,
  detail jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX import_issues_run_kind_idx ON import_issues (run_id, kind);

CREATE TABLE index_builds (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind text NOT NULL,
  dataset_version text NOT NULL,
  object_key text NOT NULL,
  reference_count integer NOT NULL,
  built_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind, dataset_version)
);

CREATE TABLE index_references (
  build_id bigint NOT NULL REFERENCES index_builds (id) ON DELETE CASCADE,
  position integer NOT NULL,
  slug text NOT NULL REFERENCES wines (slug),
  image_sha256 text NOT NULL REFERENCES images (sha256),
  PRIMARY KEY (build_id, position),
  UNIQUE (build_id, slug)
);

CREATE TABLE image_embeddings (
  image_sha256 text NOT NULL REFERENCES images (sha256),
  model text NOT NULL,
  embedding vector(384) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (image_sha256, model)
);
```
Миграция `002_allow_repeated_versions.sql` (добавлена при реализации) снимает уникальность успешной версии: importer пропускает работу, только если версия совпадает с последним успешным run, поэтому откат overrides или CSV к прежнему состоянию снова применяется к БД, а индексы этой версии переиспользуются.

`review_status = 'rejected'` в схему не входит: `reject` в overrides просто не создаёт строку `wine_images`, а факт отказа виден в `image_overrides`.

#### 4. `.env.example`
Добавить `VINLOG_S3_PORT=9000`, `VINLOG_S3_CONSOLE_PORT=9001`, `VINLOG_S3_ACCESS_KEY=vinolog`, `VINLOG_S3_SECRET_KEY=vinolog-secret`.

### Success Criteria

#### Automated Verification:
- [x] Тесты миграций проходят: `docker compose run --rm --no-deps importer python -m pytest tests -q -p no:cacheprovider`. Тест на sha256, на порядок применения и на отказ при изменённом файле использует временную БД `vinolog_test`, которую создаёт фикстура.
- [x] `docker compose up -d db minio && docker compose run --rm importer` завершается с кодом 0.
- [x] `docker compose exec db psql -U vinolog -Atc "SELECT count(*) FROM schema_migrations"` возвращает `1`.
- [x] `docker compose exec db psql -U vinolog -Atc "SELECT extname FROM pg_extension WHERE extname='vector'"` возвращает `vector`.
- [x] Повторный `docker compose run --rm importer` завершается с кодом 0 и не меняет `schema_migrations`.

#### Manual Verification:
- [ ] Консоль MinIO на `http://127.0.0.1:9001` открывается, видны три бакета.
- [ ] На существующем volume `postgres-data` миграция удаляет старые таблицы без ошибок.

---

## Phase 2: Importer

### Overview
Полный импорт: версия датасета, каталог, изображения и превью, привязка, overrides, проверочные наборы.

### Changes Required

#### 1. `importer/versioning.py`
- `MAPPING_ALGO_VERSION = "mapping-v1"`, `PREVIEW_VERSION = "webp-400x600-q80-v1"`.
- `file_sha256(path)` читает поблочно, по 1 МБ.
- `archive_sha256(paths)` — sha256 от конкатенации sha256 томов в порядке `part1`, `part2`, `part3`.
- `dataset_version(...)` — sha256 от строки `catalog|archive|overrides|mapping|preview`.
- Если `db/image-overrides.csv` отсутствует, хэшируется пустая строка.

#### 2. `importer/catalog_csv.py`
- Читает CSV в `utf-8-sig` через `csv.DictReader`. Заголовки сопоставляются по точным русским названиям после `strip()`: `Название вина`, `Категория`, `Цвет`, `Регион`, `Сорт винограда`, `Описание`, `Винодельня`, `Slug`, `Название фото`. Если колонки не хватает, импорт падает.
- `parse_rows(reader) -> CatalogParseResult`:
  - строки нумеруются с 1;
  - у значений обрезаются пробелы, пустое значение становится `None`;
  - `grape_varieties` делится по запятой, пустые элементы отбрасываются;
  - строка без slug даёт issue `missing_slug`;
  - для дублей slug побеждает первая строка (как в текущем `ORDER BY slug, id`), считается `raw_record_count`, пишется issue `duplicate_slug` с `row_numbers` и `payload_differs`.
- Возвращает `raw_rows` (для `catalog_rows_raw.payload`), `wines`, `issues`.

#### 3. `importer/archive.py`
- `ORIGINAL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}` (сравнение через `casefold`). `DERIVATIVE_PREFIXES` переносится из `services/retrieval/app/catalog.py:12`.
- `UPLOADS_MARKER = "strapi/uploads/"`.
- `iter_originals(part1_path) -> Iterator[ArchiveMember]` открывает `rarfile.RarFile(part1)`, следующие тома rarfile находит сам. Отбирает файлы, в пути которых есть `UPLOADS_MARKER`, с разрешённым расширением и без префикса производной копии. `strapi_path` — путь после маркера. Содержимое читается через `archive.read(info)` по одному файлу: архив не solid, распаковка на диск не нужна.
- `count_skipped` возвращает статистику пропущенных файлов для `import_runs.stats`.

#### 4. `importer/images.py`
- `ingest_image(member, store, connection, archive_sha)`:
  - sha256 содержимого;
  - если строки в `images` нет — декодировать через Pillow, применить `ImageOps.exif_transpose`, записать `width` и `height`;
  - `object_key = f"originals/{sha[:2]}/{sha}{ext}"`, где `ext` — расширение в нижнем регистре, `.jpeg` приводится к `.jpg`;
  - превью: `thumbnail((400, 600), Image.Resampling.LANCZOS)`, прозрачность сохраняется, `WEBP quality=80`, ключ `previews/{PREVIEW_VERSION}/{sha[:2]}/{sha}.webp`;
  - `put_bytes` вызывается, только если `exists` вернул `False`;
  - `INSERT ... ON CONFLICT DO NOTHING` в `images` и upsert в `image_sources`.
- Если файл не декодируется, пишется issue `image_decode_failed` с `strapi_path`, импорт продолжается.

#### 5. `importer/mapping.py`
- Переносятся без изменения логики: `CYRILLIC_TO_LATIN`, `HASH_SUFFIX`, `TOKEN_PATTERN`, `normalize_key`, `latin_tokens`, `media_stem`, `_fuzzy_score`, `_token_similarity`, `resolve_references` (`services/retrieval/app/catalog.py:12-24`, `72-195`).
- Вход меняется с `Media(filename, relative_path, size_bytes)` на `SourceImage(strapi_path, filename, image_sha256, size_bytes)`.
- Решение при реализации (2026-09-22): точные совпадения (`image_filename`, `slug`) могут делить один и тот же файл, как в старом коде. Так в Strapi 27 раз один файл используется для разных вин, и OCR разделяет такие дубли при поиске. Fuzzy-привязка не берёт sha, который уже занят.
- `mark_suspicious(mappings)` после overrides помечает `suspicious` автоматические привязки, если sha делят несколько вин или `mapping_kind == "fuzzy_filename"` и `mapping_score < 0.85`. Для каждой общей картинки пишется issue `shared_image` со списком slug. `MAPPING_ALGO_VERSION = "mapping-v2"`.

#### 6. `importer/overrides.py`
- Формат `db/image-overrides.csv`: заголовок `slug,action,strapi_filename,note`.
  - `set` назначает основным фото файл с этим `filename` (`image_sources.filename`), `mapping_kind='manual'`, `mapping_score=1`, `review_status='confirmed'`.
  - `reject` убирает автоматическую привязку.
  - `confirm` переводит автоматическую привязку в `confirmed`.
- Проверки: slug есть среди активных вин, имя файла однозначно, у `set` заполнено `strapi_filename`, на один slug одно действие. Любая ошибка останавливает импорт (`SystemExit` с номером строки): файл лежит в git, его можно просто исправить.
- Overrides применяются после `resolve_references`. `set` занимает файл: если этот sha был автоматически привязан к другому вину, та привязка снимается, и пишется issue `override_displaced`.
- В репозиторий добавляется `db/image-overrides.csv`, пока только с заголовком.

#### 7. `importer/eval_sets.py`
- Загружает содержимое `eval.zip` в `vinolog-eval/eval/...`, а содержимое `Реальные фото.zip` — в `vinolog-eval/real-photos/...`, пропуская `__MACOSX/` и `._*`. Объекты, которые уже есть, пропускаются. Если `Реальные фото.zip` нет, пишется issue `eval_set_missing`, импорт не падает.

#### 8. `importer/run.py` и `__main__.py`
Порядок работы:
1. Применить миграции, создать бакеты.
2. Проверить обязательные входы: `strapi_output0709.csv` и три тома RAR. `eval.zip` не обязателен, при его отсутствии пишется issue.
3. Вычислить хэши и `dataset_version`. Если есть run со статусом `succeeded` и этой версией — вывести `Dataset <ver> already imported` и выйти с кодом 0.
4. Вставить `import_runs` со статусом `running` отдельной транзакцией.
5. Если `archive_sha256` совпадает с последним успешным run, этап картинок пропускается и `image_sources` берётся из БД. Иначе вызывается `iter_originals` и `ingest_image` с прогрессом каждые 200 файлов.
6. Загрузить eval-наборы.
7. **Одна транзакция:**
   - вставить `catalog_rows_raw`;
   - upsert в `wines` (`is_active=true`, `updated_run_id`); вина, которых нет в CSV, получают `is_active=false`;
   - `resolve_references` по активным винам, затем overrides, затем suspicious;
   - `DELETE FROM wine_images` и вставить новую привязку;
   - перезаписать `image_overrides`, вставить `import_issues`;
   - issue `orphan_image` не пишется — сирот можно получить запросом;
   - записать `stats` (`catalog_rows`, `wines`, `inactive_wines`, `duplicate_slugs`, `images`, `mapped`, по `mapping_kind`, `suspicious`, `orphans`), `status='succeeded'`, `finished_at`.
8. При исключении run получает `status='failed'` и `error` отдельной транзакцией, процесс выходит с кодом 1.

#### 9. Тесты `services/importer/tests/`
- `test_mapping.py`: сюда переезжают тесты `test_media_stem_removes_strapi_hash`, `test_normalize_key_ignores_filename_separators`, `test_resolver_prefers_original_image_filename` из `services/retrieval/tests/test_catalog.py:28-44`. Новые случаи: один sha под двумя именами не достаётся двум винам; fuzzy ниже 0.85 помечается `suspicious`.
- `test_catalog_csv.py`: обрезка пробелов, пустое значение даёт `None`, сорта превращаются в список, дубли slug (первая строка побеждает, issue с `payload_differs`), пустой slug, отсутствующая колонка.
- `test_overrides.py`: `set`, `reject`, `confirm`; неизвестный slug; неоднозначное имя файла; два действия на один slug; `set` вытесняет чужую привязку.
- `test_versioning.py`: версия меняется при изменении любого из входов и одинакова при повторном расчёте.
- `test_images.py`: превью не больше 400×600, прозрачность сохраняется, EXIF-поворот применяется, ключи строятся по схеме.
- `test_run.py`: интеграционный тест на временной БД `vinolog_test` с поднятым MinIO и маленьким сгенерированным RAR. Если `rar` для создания архива недоступен, `iter_originals` подменяется списком `ArchiveMember`. Проверяются: полный прогон, повтор без работы, смена overrides без чтения архива, пропавшее вино получает `is_active=false`.

### Success Criteria

#### Automated Verification:
- [x] Unit- и интеграционные тесты проходят: `docker compose run --rm importer python -m pytest tests -q -p no:cacheprovider`.
- [x] Полный импорт на реальных данных: `docker compose run --rm importer` завершается с кодом 0.
- [x] `SELECT status, stats FROM import_runs ORDER BY id DESC LIMIT 1` возвращает `succeeded`; `stats.images` не больше 6202, `stats.mapped` не меньше 2098. Факт: `images=5799`, `mapped=2096`. Разница в 2 привязки — fuzzy больше не переиспользует уже занятый файл.
- [x] `SELECT count(*) FROM images` совпадает с числом объектов с префиксом `originals/` в `vinolog-images` и с числом объектов `previews/`: `docker compose exec minio mc ls --recursive local/vinolog-images/originals | wc -l`.
- [x] Повторный `docker compose run --rm importer` выводит `already imported` и работает не дольше 60 с.

#### Manual Verification:
- [x] Первый полный импорт на машине разработчика укладывается в 20 минут. Факт: 265 с на картинки и 10 с на хэширование. Замерить и записать в `stats`/лог. Если заметно дольше из-за запуска `unrar` на каждый файл, перейти на один проход `unrar x` во временный каталог внутри контейнера и удалять его в конце.
- [ ] Выборочно 10 вин: превью и оригинал в MinIO соответствуют бутылке из карточки.
- [x] Строка в `db/image-overrides.csv` меняет привязку после повторного импорта, архив при этом не перечитывается (видно по логу). Проверено на `pino-nuar-2025,reject`: импорт занял 13 с, новых эмбеддингов 0.

---

## Phase 3: SIFT-сервис `retrieval` и `retrieval-index`

### Overview
Индексатор и сервис поиска читают каталог и привязку из Postgres, картинки и индекс — из MinIO. Индекс версионируется по `dataset_version`.

### Changes Required

#### 1. `services/retrieval/requirements.txt`
Добавить `boto3==1.40.*` и `pgvector==0.4.*`. Второй пакет используется в этапе 4, но образ общий.

#### 2. `services/retrieval/app/storage.py`
Минимальный `ObjectStore` на boto3 с методами `get_bytes` и `download_file`, настройки из `S3_*`. Тот же интерфейс, что в importer, но отдельный код: сервисы разделены.

#### 3. `services/retrieval/app/catalog.py`
- Удалить функции привязки, `Media`, `load_catalog` и `DERIVATIVE_PREFIXES`/`HASH_SUFFIX`/`TOKEN_PATTERN`/`CYRILLIC_TO_LATIN`, если после переноса они больше не используются. `_token_similarity` нужен `text_search.py:6`: перенести его в `text_search.py`.
- `Wine`: убрать `image_filename`, `grape_varieties: tuple[str, ...]`, добавить `has_image: bool`. `as_card()` берёт сорта из кортежа, а `imageUrl` и `imagePreviewUrl` строит от `has_image`: `/api/wines/{slug}/image` и `/api/wines/{slug}/image?size=preview`.
- Новые функции:
  - `current_dataset_version(database_url) -> str` — последний `succeeded` run, если его нет — `RuntimeError`;
  - `load_wines(database_url) -> list[Wine]` — активные вина с `LEFT JOIN wine_images … is_primary`;
  - `load_references(database_url) -> list[Reference]` с полями `wine`, `image_sha256`, `object_key`, `mapping_kind`, `mapping_score`.

#### 4. `services/retrieval/app/index_store.py`
- `SIFT_INDEX_KIND = "sift-v3"`.
- `find_build(database_url, kind, version) -> IndexBuild | None`.
- `register_build(database_url, kind, version, object_key, references)` — одной транзакцией вставляет `index_builds` и `index_references`.
- `object_key_for(kind, version) -> f"{kind}/{version}.npz"` в бакете `vinolog-indexes`.

#### 5. `services/retrieval/app/index.py`
`IndexedReference.relative_path` заменяется на `image_sha256`, `Candidate.relative_path` — на `image_sha256`. Меняется JSON в `save_index`/`load`, поэтому kind повышается до `sift-v3`.

#### 6. `services/retrieval/app/image_features.py`
`read_image(path)` заменяется на `decode_reference(content: bytes)` с `IMREAD_COLOR` и понятной ошибкой.

#### 7. `services/retrieval/app/build_index.py`
- `version = current_dataset_version()`. Если есть `find_build(SIFT_INDEX_KIND, version)` — вывести `already built` и выйти.
- Для каждой ссылки: `store.get_bytes("vinolog-images", object_key)`, затем `decode_reference`, затем `extract_features`. Прежние пропуски сохраняются (меньше 8 дескрипторов, ошибка декодирования), их число выводится в лог.
- `save_index` во временный файл, `put_file` в `vinolog-indexes`, затем `register_build`, чтобы запись в БД появлялась только после загрузки файла.

#### 8. `services/retrieval/app/main.py`
- В lifespan: `version = current_dataset_version()`, `build = find_build(SIFT_INDEX_KIND, version)`. Если сборки нет — `RuntimeError("Retrieval index for <ver> is missing")`. Индекс скачивается в `/tmp/sift-{version}.npz` и загружается. `SearchService` получает `catalog=load_wines()` и `dataset_version=version`.
- Удалить `/v1/wines/{slug}/image` (`main.py:52-70`), `/v1/catalog` (`main.py:75-88`), импорт `CatalogBrowser`, `IMAGE_MEDIA_TYPES`.

#### 9. `services/retrieval/app/service.py`
- `_wine_card_with_image` (`service.py:26-28`) и `service.py:103` используют `wine.as_card()` и больше не зависят от `candidate.relative_path`.
- `"catalog": "dataset-v1"` (`service.py:139`) заменяется на `self.dataset_version`.

#### 10. `services/retrieval/app/config.py`
Убрать `dataset_root` и `index_path`, добавить S3-настройки.

#### 11. Удалить `services/retrieval/app/catalog_browser.py`
Удалить и тест `test_catalog_record_exposes_image_mapping_diagnostics` (`tests/test_catalog.py:61`). Admin-логика переезжает в Nuxt на этапе 5.

#### 12. `compose.yaml`
- `retrieval-index`: `depends_on` `importer` (`service_completed_successfully`), убрать volumes `dataset` и `retrieval-index`, убрать `DATASET_ROOT` и `INDEX_PATH`, добавить S3-переменные.
- `retrieval`: то же, `depends_on` — `retrieval-index` и `minio`.

#### 13. Тесты
- `tests/test_catalog.py`: `as_card` с `has_image=True/False` и сортами-кортежем.
- `tests/test_search.py`: подставить `Wine(..., has_image=...)` и `image_sha256` вместо `relative_path`. Добавить тест: `version.catalog` берётся из `dataset_version`.
- Новый `tests/test_index_store.py`: ключ объекта для kind и версии; `find_build`/`register_build` на временной БД.

### Success Criteria

#### Automated Verification:
- [x] Python-тесты проходят: `docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/workspace" -w /workspace -e PYTHONPATH=/workspace/services/retrieval retrieval python -m pytest services/retrieval/tests -q -p no:cacheprovider`.
- [x] `docker compose run --rm retrieval-index` завершается с кодом 0. `SELECT kind, reference_count FROM index_builds` возвращает строку `sift-v3`, `reference_count` не меньше 2000.
- [x] Повторный запуск `retrieval-index` выводит `already built`.
- [x] `docker compose up -d retrieval`, после чего `curl -fsS http://127.0.0.1:8080/health` возвращает `{"status":"ok"}`.
- [x] `curl -fsS -F image=@services/retrieval/tests/fixtures/zakat-denisov-vajneri.webp http://127.0.0.1:8080/v1/search` возвращает `version.catalog`, равный текущему `dataset_version`.
- [x] `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/v1/wines/any/image` возвращает `404`: маршрута больше нет.

#### Manual Verification:
- [ ] Top-1 на шести фикстурах `services/retrieval/tests/fixtures/` совпадает с результатом до изменений. Записать оба прогона. После изменений: 4 из 6 (abrau и perovskih ошибочны). Прогона «до» на этой машине нет — старых индексов не было.

---

## Phase 4: Retriever на pgvector

### Overview
Эмбеддинги DINOv2 хранятся в `image_embeddings` и считаются только для новых изображений. Ретривер ищет по ним через pgvector, SIFT-часть его индекса лежит в MinIO.

### Changes Required

#### 1. `services/retrieval/app/embedding.py`
Константа `EMBEDDING_MODEL = f"dinov2-small@{download_model.MODEL_SHA256[:12]}/label-prep-512"`. Она зависит от модели и параметров `LabelConfig(visual_size=512)` из `build_retriever_index.py:33`, при их изменении нужна новая строка.

#### 2. `services/retrieval/app/label_normalize.py`
`prepare_reference(path, …)` (`label_normalize.py:126`) разделяется: `prepare_reference_image(source: np.ndarray, …)` с текущей логикой и `decode_reference_unchanged(content: bytes)` через `cv2.imdecode(..., IMREAD_UNCHANGED)`. Вызов по пути, если после этапа 6 он больше нигде не используется, удаляется.

#### 3. `services/retrieval/app/embedding_store.py`
- `EmbeddingStore(database_url, model)` использует `pgvector.psycopg.register_vector`.
- `missing(shas) -> set[str]`.
- `upsert_many(rows)` — `INSERT … ON CONFLICT DO NOTHING`, пачками по 100.
- `nearest(build_id, query, limit) -> list[tuple[str, float]]`:
```sql
SELECT ir.slug, 1 - (e.embedding <=> %(q)s) AS similarity
FROM index_references ir
JOIN image_embeddings e ON e.image_sha256 = ir.image_sha256 AND e.model = %(model)s
WHERE ir.build_id = %(build_id)s
ORDER BY e.embedding <=> %(q)s
LIMIT %(limit)s
```
- `scores(build_id, query, slugs) -> dict[str, float]` — тот же SELECT с условием `ir.slug = ANY(%(slugs)s)` без ORDER/LIMIT.
- Косинусное расстояние pgvector `<=>` на нормированных векторах даёт `1 - similarity`, то есть тот же `embeddings @ query`, что `retriever_index.py:106-112`.

#### 4. `services/retrieval/app/retriever_index.py`
Убрать `embeddings` из `RetrieverIndex.__init__`, `load`, `save_index` и метод `embedding_scores`. `relative_path` заменяется на `image_sha256`. `RETRIEVER_INDEX_KIND = "retriever-v2"`.

#### 5. `services/retrieval/app/retriever.py`
- `VisualRetriever` получает `embedding_store: EmbeddingStore | None` и `build_id`.
- В `search` (`retriever.py:73-94`):
  - `embedding_slugs` берутся из `nearest(build_id, q, embedding_limit)`;
  - после SIFT для всех slug из `by_slug`, которых нет среди `nearest`, вызывается `scores(...)`;
  - остальная комбинация и сортировка не меняются.
- Итоговые баллы должны совпадать с прежними до 1e-5: сейчас для комбинации используются только баллы кандидатов из `by_slug`.

#### 6. `services/retrieval/app/build_retriever_index.py`
- `version = current_dataset_version()`. Если есть `find_build(RETRIEVER_INDEX_KIND, version)` — выход.
- `missing = store.missing(all_shas)`. Для каждой ссылки: `get_bytes`, `decode_reference_unchanged`, `prepare_reference_image`, SIFT. Эмбеддинг считается, только если `sha in missing`, запись идёт пачками.
- `save_index` без эмбеддингов, загрузка в MinIO, `register_build`.
- Ссылка без эмбеддинга (например, ошибка кодирования) не попадает в `index_references` этой сборки, чтобы SIFT и pgvector видели один и тот же набор.

#### 7. `services/retrieval/app/retriever_main.py`
- В lifespan: версия, сборка, скачивание `.npz`, `EmbeddingStore`. Encoder загружается всегда, условие `index.embeddings is not None` (`retriever_main.py:46`) убирается.
- Удалить `/v1/wines/{slug}/image` (`retriever_main.py:62-73`) и `IMAGE_MEDIA_TYPES`. Карточки кандидатов строятся через `wine.as_card()`.

#### 8. `services/retrieval/app/retriever_config.py`
Убрать `dataset_root`, `index_path`; добавить S3.

#### 9. `compose.yaml`
- `retriever-index` и `retriever`: `depends_on` `importer`, убрать `dataset` и `retriever-index-data`, убрать `DATASET_ROOT` и `RETRIEVER_INDEX_PATH`, добавить S3-переменные. `retriever-models` остаётся.

#### 10. Тесты
- `tests/test_embedding_store.py` на временной БД с pgvector:
  - `nearest` возвращает тот же порядок, что `numpy` на тех же векторах;
  - `scores` для подмножества slug совпадает с `numpy` до 1e-5;
  - `missing` видит только отсутствующие sha для заданной модели.
- `tests/test_retriever.py`: `VisualRetriever` с фейковым `EmbeddingStore` на `numpy` и маленьким `RetrieverIndex` даёт те же кандидаты и баллы, что прежняя реализация `embedding_scores` на тех же данных.

### Success Criteria

#### Automated Verification:
- [x] Python-тесты проходят (та же команда, что в этапе 3).
- [x] `docker compose run --rm retriever-index` завершается с кодом 0. `SELECT count(*) FROM image_embeddings` равно числу уникальных `image_sha256` в сборке `retriever-v2`: 2066 эмбеддингов на 2096 ссылок, у вин с общей картинкой эмбеддинг один.
- [x] Второй запуск после изменения только `db/image-overrides.csv` (новая версия) добавляет в `image_embeddings` не больше строк, чем новых изображений в привязке. Число строк до и после выводится в лог.
- [x] `curl -fsS http://127.0.0.1:8081/health` возвращает `ok`.

#### Manual Verification:
- [x] Top-1 ретривера на шести фикстурах совпадает с результатом до изменений. Проверено скриптом-сравнением: кандидаты и баллы через pgvector полностью совпадают с прежним полным перебором в numpy на всех 6 фикстурах. Top-1: 3 из 6 (запускать `tests/tune_weights_experiment.py` или вручную через `/v1/search` на 8081).
- [x] `embeddingMs` в timing не выросло больше чем на 20 мс против версии с `.npz`.
- [x] Память процесса `retriever` не выросла (`docker stats`).

---

## Phase 5: Web (Nuxt)

### Overview
По порядку CODE_RULES: сначала контракты, потом server API, потом UI. Картинки идут из MinIO через Nuxt, админка и сомелье переходят на новые таблицы.

### Changes Required

#### 1. `apps/web/shared/contracts/index.ts`
- `WineCard`: добавить `imagePreviewUrl: string | null`.
- `CatalogImageStatus = 'all' | 'with_image' | 'without_image' | 'suspicious' | 'not_indexed'`.
- `CatalogSummary`:
```ts
export interface CatalogSummary {
  datasetVersion: string
  importedAt: string
  rawRecords: number
  uniqueWines: number
  inactiveWines: number
  duplicateSlugs: number
  images: number
  orphanImages: number
  winesWithImage: number
  suspiciousMappings: number
  indexedWines: number
}
```
- `CatalogAdminWine`:
```ts
export type CatalogMappingKind = 'image_filename' | 'slug' | 'fuzzy_filename' | 'manual'
export type CatalogReviewStatus = 'auto' | 'suspicious' | 'confirmed'

export interface CatalogAdminWine extends WineCard {
  sourceImageFilename: string | null
  imageStrapiPath: string | null
  mappingKind: CatalogMappingKind | null
  mappingScore: number | null
  reviewStatus: CatalogReviewStatus | null
  rawRecordCount: number
  isIndexed: boolean
}
```
- Обновить все литералы `WineCard`: `scans.post.ts:17,31`, `sommelier-mock.ts:17,30,43`, тесты `zodiac-wine.test.ts:16`, `sommelier-ai.test.ts:17`, `sommelier-guardrails.test.ts:23`.

#### 2. `apps/web/nuxt.config.ts`
В `runtimeConfig` (приватно, не в `public`): `storage: { endpoint, region, accessKey, secretKey, imagesBucket }` из `NUXT_STORAGE_ENDPOINT`, `NUXT_STORAGE_REGION`, `NUXT_STORAGE_ACCESS_KEY`, `NUXT_STORAGE_SECRET_KEY`, `NUXT_STORAGE_IMAGES_BUCKET` (по умолчанию `vinolog-images`). Добавить их в `.env.example` для запуска вне Docker (`http://127.0.0.1:9000`).

#### 3. `apps/web/package.json`
Добавить `@aws-sdk/client-s3`.

#### 4. `apps/web/server/utils/catalog-db.ts`
Вынести `getCatalogPool` из `sommelier-catalog.ts:17-24`, чтобы пул был один на весь сервер.

#### 5. `apps/web/server/utils/catalog-storage.ts`
- Ленивый `S3Client` с `forcePathStyle: true`.
- `getImageObject(key)` возвращает `{ body: ReadableStream, contentType, contentLength, etag }`. Отсутствие ключа — `null`, остальные ошибки пробрасываются.

#### 6. `apps/web/server/utils/wine-images.ts`
- `parseImageSize(value: unknown): 'original' | 'preview' | null` — чистая функция. `undefined` означает `original`, неизвестное значение — `null`.
- `findPrimaryImage(slug)`:
```sql
SELECT i.sha256, i.object_key, i.preview_key, i.mime
FROM wine_images wi
JOIN wines w ON w.slug = wi.slug AND w.is_active
JOIN images i ON i.sha256 = wi.image_sha256
WHERE wi.slug = $1 AND wi.is_primary
```
- `wineImageUrls(slug, hasImage)` возвращает `{ imageUrl, imagePreviewUrl }` для карточек.

#### 7. `apps/web/server/api/wines/[slug]/image.get.ts`
Заменить прокси в retrieval:
- slug пустой или длиннее 200 символов — 400;
- `parseImageSize` вернул `null` — 400 с текстом «Размер изображения: preview или original.»;
- привязки нет — 404;
- объекта нет — 404, в лог сервера пишется предупреждение о рассинхроне;
- ошибка S3 или БД — 502 «Не удалось загрузить изображение вина.»;
- ответ: поток тела, `Content-Type` (`image/webp` для превью, `mime` для оригинала), `ETag: "<sha256>-<size>"`, `Cache-Control: public, max-age=86400`, 304 при совпадении `If-None-Match`.

#### 8. `apps/web/server/utils/catalog-admin.ts`
- `parseAdminQuery(query)` — чистая функция: страница (`page`), `q` не длиннее 120 символов, `imageStatus` из допустимого списка.
- `browseCatalog(params)`: SQL по `wines`, `LEFT JOIN wine_images` (primary), `image_sources`. `isIndexed` — `EXISTS` в `index_references` последней сборки `sift-v3` для текущей `dataset_version`. Фильтры по `imageStatus` и поиск `ILIKE` по `concat_ws(' ', slug, name, winery, category, color, region, array_to_string(grape_varieties, ' '))`. Порядок `winery, name, slug`, 24 на страницу, `count(*) OVER()`.
- `catalogSummary()` — один запрос с подзапросами. `rawRecords` и `duplicateSlugs` берутся из `import_runs.stats` последнего успешного run, `orphanImages` — `images` без строк в `wine_images`.
- Неактивные вина в админке не показываются, их число есть в сводке.

#### 9. `apps/web/server/api/admin/wines.get.ts`
Валидирует запрос через `parseAdminQuery`, вызывает `browseCatalog` и `catalogSummary`. Ошибка БД — 502 «Не удалось загрузить каталог. Проверьте PostgreSQL.»

#### 10. `apps/web/server/utils/sommelier-catalog.ts`
- `FROM wines w LEFT JOIN wine_images wi ON wi.slug = w.slug AND wi.is_primary WHERE w.is_active`.
- `grape_varieties` в `ILIKE` и `to_tsvector` через `array_to_string(w.grape_varieties, ', ')`.
- `CatalogRow.grape_varieties: string[]`, `has_image: boolean`. `toWineCard` берёт URL из `wineImageUrls`.

#### 11. UI
- Превью (`imagePreviewUrl`, если нет — `imageUrl`): `WineResultCard.vue:40-42`, `SommelierWineCard.vue:12-13`, `AdminWineCard.vue:22-29`, `pages/astro-sommelier.vue:66`.
- Оригинал: `CatalogImageLightbox.vue:61`.
- `AdminWineCard.vue:53-104`: статус «Фото привязано / Без фото / Подозрительная привязка», отдельная пометка «В индексе поиска». Поля «Имя фото в CSV», «Файл Strapi», «Тип привязки», «Оценка», «Проверка».
- `pages/admin/index.vue:7-114`: новые плитки сводки (уникальных вин, с фото, подозрительных, в индексе, файлов без вина), строка версии датасета и даты импорта, `select` с пятью значениями `CatalogImageStatus`.

#### 12. `compose.yaml` (`web`)
- `depends_on`: `importer` completed, `minio` healthy, `retrieval` healthy.
- Добавить `NUXT_STORAGE_*` (`http://minio:9000`) и `NUXT_DATABASE_URL` или оставить `PG*`, как сейчас.
- Удалить mount `dataset:/workspace/Vinolog/data/installed:ro`.

#### 13. Тесты (vitest)
- `server/utils/wine-images.test.ts`: `parseImageSize` (undefined, preview, original, мусор); `wineImageUrls` (`hasImage` true/false, экранирование slug).
- `server/utils/catalog-admin.test.ts`: `parseAdminQuery` (страница 0, отрицательная, строка; `q` длиннее 120 символов обрезается; неизвестный `imageStatus` становится `all`).
- `server/utils/sommelier-catalog.test.ts`: обновить под `grape_varieties: string[]` и `has_image`.

### Success Criteria

#### Automated Verification:
- [x] `docker compose exec web sh -c 'npm run check'` проходит (lint, typecheck, test, build).
- [x] `curl -s -o /dev/null -w '%{http_code} %{content_type}' 'http://127.0.0.1:3000/api/wines/<slug-с-фото>/image?size=preview'` возвращает `200 image/webp`.
- [x] `curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:3000/api/wines/<slug-с-фото>/image?size=huge'` возвращает `400`.
- [x] `curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:3000/api/wines/<slug-без-фото>/image'` возвращает `404`.
- [x] `curl -fsS 'http://127.0.0.1:3000/api/admin/wines?imageStatus=suspicious' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert all(w["reviewStatus"]=="suspicious" for w in d["wines"])'` завершается с кодом 0.
- [x] Картинка отдаётся для вина с привязкой, но без индекса: `SELECT wi.slug FROM wine_images wi WHERE wi.is_primary AND NOT EXISTS (SELECT 1 FROM index_references ir WHERE ir.slug = wi.slug) LIMIT 1`, затем `curl` на этот slug возвращает `200`.

#### Manual Verification:
- [ ] Сканирование на 360–430 px: карточка результата показывает превью, лайтбокс — оригинал.
- [ ] Сомелье показывает фото только у вин, у которых оно есть.
- [ ] Админка: фильтры, сводка, версия датасета, раскрытие диагностики. Нет горизонтального скролла на 360 px, фильтр доступен с клавиатуры.
- [x] Повторная загрузка картинки даёт 304 (DevTools, Network).

---

## Phase 6: Скрипты, чистка, документация

### Overview
Перевести скрипты оценки и аудита на новое хранилище, удалить старый пайплайн, обновить документацию.

### Changes Required

#### 1. `scripts/audit_mapping.py`
- Уточнение при реализации: эмбеддинги аудит считает своей моделью (`--model`), как и раньше, а не берёт из `image_embeddings`. Для сирот эмбеддингов в БД нет, а смешивать модели в одном сравнении нельзя.
- Берёт ссылки из `load_references()` и картинки из MinIO. Вместо `load_catalog` + `is_original_media` (`audit_mapping.py:22,151-156`) сироты получаются запросом `SELECT … FROM images i LEFT JOIN image_sources s … WHERE NOT EXISTS (SELECT 1 FROM wine_images wi WHERE wi.image_sha256 = i.sha256)`.
- Аргументы `--npz`/`--dataset` заменяются чтением текущей сборки `retriever-v2` и эмбеддингов из `image_embeddings`, вычислять их повторно не нужно.
- Кроме JSON, пишет `reports/image-overrides-proposed.csv` в формате `slug,action,strapi_filename,note` с действиями `set` для `proposed_fixes`. `note` содержит `cosine` и `nearest_peer_slug`. Файл не применяется автоматически: человек переносит строки в `db/image-overrides.csv`.
- Если есть `--self-check`, обновить его под новый формат.

#### 2. `scripts/eval.py`, `scripts/eval_search.py`
- Убрать `--dataset` и `--index`. Индекс берётся по текущей сборке `sift-v3` (скачивание из MinIO), эталоны — через `ObjectStore.get_bytes` по `object_key` из `load_references()`. Для синтетики картинки не записываются на диск, а декодируются из байтов (`eval_search.py:121` строит `path` — заменить на ключ объекта и загрузку байтов).
- `--manifest` по-прежнему принимает локальные пути.
- `scripts/tests/test_eval_search.py` обновить под новые аргументы.

#### 3. Удаление
`Dockerfile.dataset`, `scripts/init-dataset.sh`, `scripts/build-media-manifest.py`, `db/import-dataset.sh`, `db/import-dataset.sql`. В `compose.yaml` — объявления volumes `dataset`, `retrieval-index`, `retriever-index-data` (сервисы убраны на этапе 1, ссылки на volumes — на этапах 3–5).

#### 4. Документация
- `README.md`:
  - раздел запуска: список файлов в `data/dataset/`, включая необязательный `Реальные фото.zip`;
  - первый запуск: importer, MinIO-консоль, сколько он длится;
  - повторный импорт: положить новый CSV или архив и выполнить `docker compose up`, удалять volumes не нужно;
  - `db/image-overrides.csv` и цикл аудита;
  - `psql`-примеры по `import_runs` и `wine_images`;
  - команды pytest для importer и retrieval, eval-команды без `--dataset`;
  - убрать строки 57, 92–103 про `vinolog_dataset` и `vinolog_retrieval-index`.
- `ARCHITECTURE.md`:
  - схема границ: MinIO, importer, pgvector;
  - строки 48 и 59–61: источник картинок, админка через Postgres, эмбеддинги в pgvector, версионирование индексов.
- `scripts/README.md`: удалить `init-dataset.sh` и `build-media-manifest.py`, обновить описание `audit_mapping.py`.
- `services/retrieval/README.md`: хранилища индексов и эмбеддингов.
- Новый `services/importer/README.md`: этапы, версия датасета, формат overrides, коды выхода.

### Success Criteria

#### Automated Verification:
- [x] `git ls-files | grep -E 'Dockerfile.dataset|init-dataset.sh|build-media-manifest.py|import-dataset'` ничего не выводит.
- [x] `docker compose config --services | grep -E '^(dataset-init|db-import)$'` ничего не выводит.
- [x] `docker compose config --volumes | grep -E '^(dataset|retrieval-index|retriever-index-data)$'` ничего не выводит.
- [x] `grep -rn "DATASET_ROOT\|/dataset/current\|wine_catalog\b\|wine_media" services apps scripts compose.yaml README.md ARCHITECTURE.md` ничего не находит.
- [x] Python-тесты retrieval и scripts: `docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/workspace" -w /workspace -e PYTHONPATH=/workspace/services/retrieval retrieval python -m pytest services/retrieval/tests scripts/tests -q -p no:cacheprovider`.
- [x] Тесты importer: `docker compose run --rm importer python -m pytest tests -q -p no:cacheprovider`.
- [x] `docker compose exec web sh -c 'npm run check'`.
- [x] Холодный старт (web при первом старте упал на сетевом сбое `npm ci` — ECONNRESET, после повторного `up -d web` поднялся): `docker compose down -v && docker compose up --build -d`, после чего `docker compose ps` показывает `retrieval`, `retriever`, `web` healthy или running, а `importer`, `retrieval-index`, `retriever-index` — `exited (0)`.

#### Manual Verification:
- [x] `eval_search.py --synthetic 8 --profile hard` даёт Accuracy@1 не ниже прежнего прогона из `reports/photo-search-final.json` на той же конфигурации. Факт: 0.857, как в базовой линии; Recall@5 0.875 против 0.857.
- [ ] Аудит генерирует `reports/image-overrides-proposed.csv`. Перенос двух строк в `db/image-overrides.csv` и `docker compose up` меняют привязку, SIFT-индексы пересобираются, эмбеддинги пересчитываются только для новых sha.
- [ ] Замена CSV на изменённый (удалить одно вино, поправить описание другого) и `docker compose up`: новый run, вино помечено неактивным, описание обновлено, volumes не удалялись.

---

## Testing Strategy

### Unit Tests
- Importer: разбор CSV, версия, привязка (перенесённые и новые случаи), overrides, превью и ключи объектов.
- Retrieval: `as_card`, `index_store`, эквивалентность `EmbeddingStore` и numpy, эквивалентность `VisualRetriever` до и после.
- Web: `parseImageSize`, `wineImageUrls`, `parseAdminQuery`, `toWineCard` с массивом сортов.

### Integration Tests
- Importer `test_run.py` на временной БД и MinIO: полный прогон, повтор без работы, смена overrides без чтения архива, деактивация вина.
- `test_embedding_store.py` и `test_index_store.py` на временной БД с pgvector.
- Временная БД создаётся фикстурой в `vinolog_test` через тот же сервер `db` и удаляется после сессии. Объекты теста живут в бакетах с префиксом `test-`.

### Manual Testing Steps
1. `docker compose down -v`, затем `docker compose up --build -d`, наблюдать `docker compose logs -f importer`.
2. Проверить сводку `/admin` и сравнить с `import_runs.stats`.
3. Отсканировать фикстуры и поле из `Реальные фото`.
4. Изменить overrides, выполнить `docker compose up`, проверить пересборку и отсутствие лишних эмбеддингов.
5. Изменить CSV, выполнить `docker compose up`, проверить деактивацию.

## Performance Considerations

- **Чтение RAR.** `rarfile` запускает `unrar` на каждый из 6 202 файлов. Это допустимо, потому что архив не solid и каждый файл читается независимо. Если первый импорт не уложится в 20 минут, запасной вариант описан в этапе 2.
- **Хэширование томов RAR (~2,2 ГБ)** при каждом запуске importer занимает порядка 5–15 секунд. Это цена надёжного определения версии, кэш по `mtime` не вводится.
- **Превью** генерируются один раз на sha. Смена `PREVIEW_VERSION` пересоздаёт их под новым префиксом ключа, старые объекты остаются.
- **Эмбеддинги** считаются только для sha без строки при текущем `EMBEDDING_MODEL`. Это главный выигрыш по времени при повторных сборках.
- **Запросы к pgvector** — точный скан около 2 000 векторов, два запроса на поиск. Если строк станет больше 50 000, добавить HNSW-индекс по `embedding vector_cosine_ops`.
- **Индекс в памяти.** `.npz` скачивается в `/tmp` контейнера при старте, память процесса та же, что сейчас.
- **Картинки через Nuxt** отдаются потоком без буферизации. ETag и `max-age` снимают повторную нагрузку.

## Migration Notes

- Существующий `postgres-data` сохраняется: миграция `001` удаляет старые view и таблицы. Образ `pgvector/pgvector:0.8.0-pg16` совместим с данными PG16.
- После слияния разработчику нужно один раз выполнить:
```bash
docker compose down
```
```bash
docker volume rm vinolog_dataset vinolog_retrieval-index vinolog_retriever-index-data
```
```bash
docker compose up --build -d
```
Эти шаги описываются в README.
- `retriever-models` сохраняется.
- Откат — `git revert` ветки, затем `docker compose down -v` и старый холодный старт. Новые таблицы несовместимы со старым кодом, поэтому откат без пересоздания `postgres-data` не поддерживается.

## References

- Обсуждение в сессии 2026-09-22: слабые места текущего импорта и решения (MinIO, свои превью, overrides только файлом, отдельный `services/importer`, админка в Nuxt, эмбеддинги в pgvector).
- Текущий пайплайн: `compose.yaml`, `scripts/init-dataset.sh`, `db/import-dataset.sh`, `db/import-dataset.sql`, `services/retrieval/app/catalog.py:134`.
- Аудит привязки: `reports/mapping_audit_2026-09-16.json`, `scripts/audit_mapping.py`.
- Ретривер: `services/retrieval/app/retriever.py`, `retriever_index.py`, `build_retriever_index.py`, `thoughts/groom/2b_RETRIEVER.md`.
- Правила: `docs/engineering/CODE_RULES.md`.
- Связанные планы: `thoughts/shared/plans/2026-09-16-wine-scanner-retrieval-upgrade.md`, `thoughts/shared/plans/2026-09-21-photo-retrieval-tesseract.md`.
