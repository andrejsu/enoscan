# Разработка

Документ для разработчиков проекта. Запуск стека, переменные окружения и проверка скриптом кейсодержателя описаны в [README.md](../../README.md), устройство системы — в [ARCHITECTURE.md](../../ARCHITECTURE.md), правила изменения кода — в [CODE_RULES.md](CODE_RULES.md).

## Команды

```bash
npm run dev            # Nuxt dev server вне Docker (mock-режим сканера)
npm run lint           # ESLint
npm run prepare:nuxt   # пересоздать служебные типы Nuxt
npm run typecheck      # проверка типов Vue/Nuxt
npm run test           # unit-тесты web
npm run eval:sommelier # red-team набор против запущенного API сомелье
npm run build          # production build
npm run check          # lint + typecheck + test + build
```

Python-тесты сервисов распознавания и оценочных скриптов. Тестам с БД нужен запущенный `db`, они создают и удаляют временную базу `vinolog_test_*`; фикстурные тесты `services/retrieval/tests/test_fixture_photos.py` пропускаются, если `ocr-retriever` и `retriever` не запущены:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/services/retrieval:/workspace/scripts retrieval \
  python -m pytest services/retrieval/tests scripts/tests -q -p no:cacheprovider

docker compose run --rm importer python -m pytest tests -q -p no:cacheprovider
```

## Dev-контейнер web

`docker compose exec web sh` открывает shell в `/workspace/Vinolog` от UID/GID из `.env` (по умолчанию `1000:1000`; на Linux с другими значениями задайте `VINLOG_UID` и `VINLOG_GID`). Рабочая директория смонтирована с хоста вместе с `.git`: правки и коммиты сразу видны на хосте, dev-сервер обновляется без пересборки. `node_modules` и `.nuxt` живут в отдельных томах; при изменении `package-lock.json` контейнер сам выполняет `npm ci`. В образе есть Node.js 22.22.2, Git, OpenSSH, Python 3, ripgrep и `psql`; при сборке образа выполняется `npm run check`.

Для `git push` из контейнера положите приватный ключ OpenSSH в игнорируемый Git файл `github_gem_token.txt` (`chmod 600`) и укажите путь в `.env` как `GITHUB_GEM_TOKEN_PATH=./github_gem_token.txt`. Ключ монтируется только для чтения и не попадает в образ. Без него Git использует ключи из `~/.ssh` хоста.

В контейнере нет `curl` и `jq`, поэтому скрипт кейсодержателя `participant_test.sh` запускается на хосте (см. README).

## База данных

`psql` внутри web-контейнера уже настроен через `PGHOST`/`PGUSER`/`PGDATABASE`; с хоста PostgreSQL доступен на `localhost:5433` (пользователь и БД `vinolog`, пароль — `VINLOG_DB_PASSWORD`).

```bash
psql -c "SELECT id, status, dataset_version, stats->'mapped' AS mapped FROM import_runs ORDER BY id DESC LIMIT 3;"
psql -c "SELECT kind, count(*) FROM import_issues WHERE run_id = (SELECT max(id) FROM import_runs) GROUP BY kind;"
psql -c "SELECT slug, mapping_kind, review_status FROM wine_images WHERE review_status = 'suspicious' LIMIT 10;"
```

Консоль MinIO — `http://127.0.0.1:9001`, логин и пароль — `VINLOG_S3_ACCESS_KEY`/`VINLOG_S3_SECRET_KEY`.

## Привязка фото к винам и ручные исправления

Importer привязывает фото к вину по имени файла из CSV, затем по `slug`, затем по сходству токенов имени (порог 0.72). Картинки, общие для нескольких вин, и нечёткие привязки со сходством ниже 0.85 помечаются `suspicious`. Исправления вносятся в `db/image-overrides.csv` и применяются при следующем импорте:

```csv
slug,action,strapi_filename,note
<slug вина>,set,<имя файла из архива>,правильная бутылка
<slug вина>,reject,,чужое фото
<slug вина>,confirm,,общая этикетка разных урожаев подтверждена
```

`set` назначает файл по имени из архива, `reject` снимает привязку, `confirm` подтверждает автоматическую. Ошибка в файле (неизвестный slug, неоднозначное имя файла, отсутствующий в архиве файл) останавливает импорт с номером строки. Предложения исправлений готовит `scripts/audit_mapping.py` (см. `scripts/README.md`).

## Повторный импорт и чистый старт

Новый CSV или архив положите в `data/dataset/` и выполните `docker compose up -d`: importer увидит новую версию данных, индексы пересоберутся, эмбеддинги посчитаются только для новых картинок. После импорта перезапустите сервисы распознавания (`docker compose up -d --force-recreate retriever ocr-retriever ranking`): каталог и индекс они загружают один раз при старте.

`docker compose down -v` удаляет все именованные тома: БД, MinIO, модели, `node_modules` и кэш Nuxt. Исходные архивы в `data/dataset/` остаются. Если стек поднимался до перехода индексов в MinIO, один раз удалите старые тома:

```bash
docker compose down
docker volume rm vinolog_dataset vinolog_retrieval-index vinolog_retriever-index-data
```

## Оценка визуального поиска

`scripts/eval.py` и `scripts/eval_search.py` оценивают только визуальный SIFT-baseline (`BaselineSearch`) внутри своего процесса, без HTTP и без OCR. `eval_search.py` сохраняет прогноз каждого запроса, Accuracy@1, Recall@5, охват и точность автоматических ответов и задержки:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/services/retrieval:/workspace/scripts retrieval \
  python scripts/eval_search.py --synthetic 8 --profile hard \
  --label synthetic-default --output reports/photo-search-local.json
```

Скрипту нужны запущенные `db` и `minio`; индекс в памяти занимает около 2 ГБ, при нехватке памяти остановите на время `retrieval` и `retriever`. Собственный manifest — JSONL с путями относительно файла:

```json
{"path":"photos/one.jpg","expected_slug":"actual-catalog-slug","group":"capture-session-1","split":"tuning"}
{"path":"photos/unknown.jpg","expected_slug":null,"group":"capture-session-2","split":"holdout"}
```

`expected_slug: null` — проверенное неизвестное вино, отсутствие ключа — нет разметки. Одна съёмка не должна попадать в разные split. В `configs/photo-search-pilot.jsonl` пути указывают на `/dataset/current/eval` и `../data/dataset/real-photos-100`: перед запуском приведите их к своему расположению фото.

HTTP smoke-проверка формата ответов и ошибок `ranking` (правильность вина она не проверяет):

```bash
python3 scripts/smoke_search.py --base http://127.0.0.1:8080 --output reports/photo-search-http-local.json
```

## Red-team сомелье

```bash
npm run eval:sommelier
SOMMELIER_EVAL_BASE_URL=http://127.0.0.1:3001 npm run eval:sommelier
```

Для сравнения провайдеров меняйте `NUXT_SOMMELIER_PROVIDER` и `NUXT_SOMMELIER_API_KEY`, пересоздавайте web и запускайте тот же набор.

## Диагностика TypeScript в редакторе

`.nuxt` и `.output` генерируются фреймворком и не проверяются как самостоятельные проекты. Если редактор показывает ошибки внутри `.nuxt/*.d.ts`, хотя `npm run typecheck` проходит, выполните `npm run prepare:nuxt`, затем в VS Code `TypeScript: Select TypeScript Version` → `Use Workspace Version` и `Developer: Reload Window`.
