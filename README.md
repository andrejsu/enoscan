## Быстрый старт

Требования: Node.js 22.22.2+ и npm 10+. Версия зафиксирована в `.nvmrc`.

```bash
nvm use
npm install
npm run dev
```

После запуска откройте `http://localhost:3000`. При запуске без Docker маршрут остаётся в демонстрационном mock-режиме; полный Compose-стек подключает локальное распознавание.

Астро-сомелье управляется публичным runtime-флагом `NUXT_PUBLIC_ASTRO_ENABLED`. Значение `false` скрывает пункт меню и блок знака вина, перенаправляет страницу функции на главную и закрывает её API ответом `404`. После изменения `.env` пересоздайте web-контейнер: `docker compose up -d --force-recreate web`. Пересборка образа не требуется.

Read-only админка каталога доступна на `http://localhost:3000/admin`. Она читает PostgreSQL напрямую: показывает версию импортированного датасета, число вин, привязанных и подозрительных фото, эталонов в поисковом индексе и файлов без вина. Поиск работает по названию, производителю, slug и региону; фильтры — «с фото», «без фото», «требуют проверки» и «вне индекса поиска». В карточке раскрываются исходные поля и диагностика привязки файла.

## Цифровой сомелье

Страница `http://localhost:3000/sommelier` ведёт диалог о выборе вина к блюду, событию или вкусовому профилю. По умолчанию работает маркированный `mock`-режим: он не отправляет данные внешнему AI и не выдаёт демонстрационные карточки за живой поиск. История хранится только в `localStorage` браузера.

Режим задаётся через `NUXT_PUBLIC_SOMMELIER_MODE`:

- `mock` — воспроизводимые ответы без ключа и PostgreSQL;
- `live` — server-side AI и обязательный поиск по таблице `wines`;
- `off` — пункт меню, страница и API отключены.

Для `live` выберите `NUXT_SOMMELIER_PROVIDER=openai|anthropic|google`, при необходимости задайте `NUXT_SOMMELIER_MODEL` и передайте ключ выбранного провайдера в единой серверной переменной `NUXT_SOMMELIER_API_KEY`. Провайдер определяет нужный адаптер; ключ не имеет префикса `NUXT_PUBLIC_` и не попадает в браузер. В Compose PostgreSQL доступен через `PGHOST`; при локальном запуске вне Compose задайте `NUXT_DATABASE_URL`, как в `.env.example`.

Один ответ проходит локальную проверку мата, входной тематический классификатор, обязательный `searchCatalog`, проверку выбранных `slug` по фактическому результату SQL и выходной классификатор. Лимит по умолчанию — 20 запросов на сессию за 10 минут; меняется через `NUXT_SOMMELIER_MAX_REQUESTS`. Заблокированные случаи логируются без исходного текста, только с короткими SHA-256 хешами.

Mock API можно проверить без ключей:

```bash
curl -s http://localhost:3000/api/sommelier/chat \
  -H 'content-type: application/json' \
  -d '{"sessionId":"665ca750-1bd4-42d4-896b-6161de3f898a","messages":[{"role":"user","content":"Подбери вино к запечённой рыбе"}]}'
```

Русский red-team набор можно прогнать против уже запущенного mock или live сервера. Для сравнения провайдеров меняйте `NUXT_SOMMELIER_PROVIDER` и значение общего `NUXT_SOMMELIER_API_KEY`, перезапускайте сервер, затем выполняйте одну и ту же команду:

```bash
npm run eval:sommelier
SOMMELIER_EVAL_BASE_URL=http://127.0.0.1:3001 npm run eval:sommelier
```

## Docker

Требования: Docker Engine или Docker Desktop с Compose; локальный Node.js для этого способа запуска не нужен.

Поместите `prod-svoe-vino-strapi.part1.rar`, `prod-svoe-vino-strapi.part2.rar`, `prod-svoe-vino-strapi.part3.rar` и `strapi_output0709.csv` в `data/dataset/`. `eval.zip` и `Реальные фото.zip` необязательны: при наличии они загружаются в бакет `vinolog-eval`. Для сборки и входа:

```bash
docker compose up --build -d
docker compose exec web sh
```

Первый запуск импортирует каталог и картинки (около 5 минут), строит SIFT-индекс (около 2 минут) и индекс ретривера с эмбеддингами DINOv2 (около 7 минут). Следующие запуски видят, что версия данных не изменилась, и завершают эти шаги за секунды. API проверки доступен на `http://localhost:8080/v1/eval/predict`.

Проверка первой версии через UI и API:

```bash
docker compose ps
curl -s http://localhost:8080/health
curl -s -F 'image=@/absolute/path/to/bottle.jpg' http://localhost:8080/v1/search
```

Откройте `http://localhost:3000`, нажмите «Сканировать бутылку» и выберите фронтальное фото этикетки в JPEG, PNG или WebP размером до 10 МБ. При подтверждённом совпадении карточка показывает эталонное фото и доступные сведения из каталога: производителя, год, категорию, цвет, регион, сорта и описание. Лучше всего работает кадр без бликов, где этикетка занимает большую часть изображения и читаются название и год.

Проверочный набор из `eval.zip` можно прогнать официальным скриптом:

```bash
eval_dir=/tmp/vinolog-eval
mkdir -p "$eval_dir"
unzip -q -o data/dataset/eval.zip -d "$eval_dir"
bash "$eval_dir/participant_test.sh" \
  --images-dir "$eval_dir/queries" \
  --manifest "$eval_dir/queries.tsv" \
  --endpoint http://localhost:8080/v1/eval/predict \
  --output "$eval_dir/predictions.jsonl"
cat "$eval_dir/predictions.jsonl"
```

Внутри контейнера рабочая директория — `/workspace/Vinolog`; shell запускается от UID/GID из локального `.env` (по умолчанию `1000:1000`). На Linux с другим UID/GID укажите свои `VINLOG_UID` и `VINLOG_GID` в `.env`. Правки исходников и Git-коммиты сразу видны на хосте; dev-сервер обновляется без пересборки. `node_modules` и `.nuxt` хранятся в отдельных томах; `.output` создаётся только при production build и игнорируется Git. При первом запуске или изменении `package-lock.json` контейнер выполняет `npm ci` для смонтированной директории. Выход из shell — `exit`.

Git и OpenSSH уже установлены в образе. Для push каждый разработчик заменяет содержимое локального `github_gem_token.txt` своим полным приватным ключом OpenSSH (начиная со строки `-----BEGIN OPENSSH PRIVATE KEY-----`) и выставляет права `chmod 600 github_gem_token.txt`. Путь задаётся в игнорируемом Git файле `.env` как `GITHUB_GEM_TOKEN_PATH=./github_gem_token.txt`. Ключ монтируется только для чтения, исключён из сборки образа и используется Git внутри shell. Публичный ключ должен быть зарегистрирован в GitHub. Если файл ещё не заполнен, Git использует существующие ключи из `~/.ssh`. Имя и почту для коммитов можно задать внутри командами `git config user.name "Имя"` и `git config user.email "email@example.com"`; настройки сохранятся в `.git/config`. Приложение доступно на `http://localhost:3000`. Образ содержит Node.js 22.22.2, Git, Python 3 и ripgrep; при сборке выполняется `npm run check`.

```bash
docker compose exec web sh -c 'npm run check'
docker compose down
```

### Данные: PostgreSQL и MinIO

Состояние стека хранится в двух местах. **PostgreSQL** (образ с pgvector, том `vinolog_postgres-data`) содержит каталог, привязку фото к винам, журнал импортов и эмбеддинги DINOv2. **MinIO** (том `vinolog_minio-data`) хранит оригиналы картинок, превью, SIFT-индексы и проверочные наборы. Консоль MinIO — `http://127.0.0.1:9001`, логин и пароль — `VINLOG_S3_ACCESS_KEY`/`VINLOG_S3_SECRET_KEY` из `.env` (по умолчанию `vinolog`/`vinolog-secret`).

Всё заполняет одноразовый сервис `importer` (`services/importer`), он запускается перед остальными:

1. Применяет миграции из `db/migrations/`.
2. Считает версию данных — хэш CSV, томов RAR, `db/image-overrides.csv` и версий алгоритма привязки и превью. Если версия совпадает с последним успешным импортом, выходит сразу.
3. Читает оригиналы из RAR по одному файлу, без распаковки на диск. Кладёт их в бакет `vinolog-images` под ключом sha256 и генерирует превью WebP 400×600. Копии Strapi (`thumbnail_`, `small_`, `medium_`, `large_`) пропускаются. Если архив не менялся, этот шаг пропускается целиком.
4. Одной транзакцией обновляет `wines` (вина, пропавшие из CSV, получают `is_active = false`), пересчитывает привязку `wine_images`, применяет ручные исправления и пишет проблемы в `import_issues`.

Для повторного импорта положите новый CSV или архив в `data/dataset/` и выполните `docker compose up -d`. Удалять тома не нужно. Индексы поиска пересоберутся под новую версию, а эмбеддинги посчитаются только для новых картинок.

Фото привязывается к вину по имени файла из CSV, затем по `slug`, затем по сходству токенов имени. Привязки к картинке, общей для нескольких вин, и неуверенные fuzzy-привязки помечаются `suspicious`. Ручные исправления вносятся в `db/image-overrides.csv` и применяются при следующем импорте:

```csv
slug,action,strapi_filename,note
pino-nuar-2025,set,DSC_00836_4070f8fd2f.webp,правильная бутылка
method-classic-kokur,reject,,чужое фото
aligote-barrel-2025,confirm,,общая этикетка разных урожаев подтверждена
```

`set` назначает файл по имени из архива, `reject` снимает привязку, `confirm` подтверждает автоматическую. Ошибка в файле (неизвестный slug, неоднозначное имя файла) останавливает импорт с номером строки. Предложения для этого файла готовит `scripts/audit_mapping.py` (см. `scripts/README.md`).

Внутри web-контейнера `psql` уже настроен через `PGHOST`/`PGUSER`/`PGDATABASE`:

```bash
psql -c "SELECT id, status, dataset_version, stats->'mapped' AS mapped FROM import_runs ORDER BY id DESC LIMIT 3;"
psql -c "SELECT kind, count(*) FROM import_issues WHERE run_id = (SELECT max(id) FROM import_runs) GROUP BY kind;"
psql -c "SELECT slug, mapping_kind, review_status FROM wine_images WHERE review_status = 'suspicious' LIMIT 10;"
```

С хоста PostgreSQL доступен на `localhost:5433` (порт меняется через `VINLOG_DB_PORT` в `.env`). Локальный пользователь и БД — `vinolog`, пароль — `VINLOG_DB_PASSWORD` из `.env` или `vinolog` по умолчанию. Картинку вина отдаёт Nuxt: `/api/wines/<slug>/image` (оригинал) и `/api/wines/<slug>/image?size=preview`.

После изменения исходников пересборка не требуется; изменение Dockerfile или Compose примените командой `docker compose up --build -d`. Локальный `.env` необязателен и игнорируется Git. Чтобы начать с чистого листа, выполните `docker compose down -v`: это удалит БД, MinIO и модели, но не исходные архивы в `data/dataset/`.

Если стек поднимался до перехода на MinIO, один раз удалите старые тома:

```bash
docker compose down
```

```bash
docker volume rm vinolog_dataset vinolog_retrieval-index vinolog_retriever-index-data
```

## Команды

```bash
npm run dev        # Nuxt dev server
npm run lint       # ESLint
npm run prepare:nuxt # пересоздать служебные типы Nuxt
npm run typecheck  # Vue/Nuxt type checking
npm run test       # unit tests
npm run eval:sommelier # red-team фикстура против запущенного API
npm run build      # production build
npm run check      # все проверки подряд
```

## Структура

- `apps/web` — Nuxt 4: мобильные экраны и server API.
- `apps/web/shared/contracts` — общие для UI и server API TypeScript-контракты без зависимости от Nuxt (`#shared/contracts`).
- `services/importer` — одноразовый импорт каталога и картинок в PostgreSQL и MinIO.
- `services/retrieval` — локальный Python/FastAPI-сервис поиска по этикетке.
- `db/migrations` — схема PostgreSQL; `db/image-overrides.csv` — ручные исправления привязки фото.
- `docs/engineering` — обязательные правила генерации и изменения кода.
- `ARCHITECTURE.md` — компоненты системы и поток запроса.

## Текущее ограничение

Compose закрывает путь от фото до карточки и официальный маршрут оценки. Продуктовый сканер (`/api/scans`) вызывает сервис `ranking` (`services/retrieval/app/ranking.py`): он объединяет кандидатов из `ocr-retriever` (Tesseract, per-поле кандидаты — название, винодельня, год, сорт и т.д., см. `app/label_fields.py`) и из `retriever` (визуальный DINOv2+SIFT), резолвит один slug и решает `matched`/`not_found` по порогу уверенности. Сервис `retrieval` — отдельный, чисто визуальный SIFT/RANSAC-поиск: он больше не стоит за продуктовым сканером, а используется для официального маршрута оценки (`/v1/eval/predict`) и `scripts/eval_search.py`. Пороги остаются эвристическими, точность на размеченных полевых фотографиях не измерена. Для цифрового сомелье реализованы три провайдерских адаптера, но live-качество, стоимость и русский red-team набор ещё не прогнаны с реальными ключами каждого провайдера; mock-тесты не доказывают поведение внешних моделей.

### Оценка визуального поиска

`scripts/eval.py` проверяет только визуальный индекс. `scripts/eval_search.py` проверяет чисто визуальный `SearchService` (OCR он больше не трогает — см. выше) и сохраняет прогноз каждого запроса, ошибки, версии, Accuracy@1, Recall@5, охват/точность автоматических ответов и задержки. Для текущего локального Docker-образа:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/services/retrieval:/workspace/scripts retrieval \
  python scripts/eval_search.py --synthetic 8 --profile hard \
  --label synthetic-default --output reports/photo-search-local.json
```

Скрипт берёт текущий SIFT-индекс и эталонные картинки из MinIO, поэтому `db` и `minio` должны быть запущены. Каждый процесс поиска держит индекс в памяти (около 2,4 ГБ). Если Docker выделено меньше 8 ГБ, остановите `retrieval` и `retriever` на время оценки. Этот режим использует только каталог индекса и искажённые эталоны. Для доступных трёх неразмеченных фото вместо `--synthetic 8 --profile hard` укажите `--manifest configs/photo-search-pilot.jsonl --split pilot`. У них намеренно отсутствует `expected_slug`: точность для них не рассчитывается.

Собственный manifest — JSONL, пути относительно manifest либо абсолютные:

```json
{"path":"photos/one.jpg","expected_slug":"actual-catalog-slug","group":"capture-session-1","split":"tuning"}
{"path":"photos/unknown.jpg","expected_slug":null,"group":"capture-session-2","split":"holdout"}
```

`expected_slug: null` означает проверенное неизвестное вино; отсутствие ключа — отсутствие разметки. Одна съёмка не может попадать в разные split. Не угадывайте правильные ответы по прогнозу модели.

HTTP-проверка доступных фото и ошибочных загрузок:

```bash
python3 scripts/smoke_search.py --base http://127.0.0.1:8080 \
  --output reports/photo-search-http-local.json
```

Она проверяет одинаковый top-1 продуктового/оценочного маршрутов, формат и HTTP-ошибки, но не правильность найденного вина. Python-тесты сервиса и оценочного скрипта (тесты с БД создают и удаляют временную базу `vinolog_test_*`, нужен запущенный `db`):

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/services/retrieval:/workspace/scripts retrieval \
  python -m pytest services/retrieval/tests scripts/tests -q -p no:cacheprovider
```

Тесты importer:

```bash
docker compose run --rm importer python -m pytest tests -q -p no:cacheprovider
```

## Диагностика TypeScript в редакторе

Папки `.nuxt` и `.output` генерируются фреймворком и не проверяются как самостоятельные TypeScript-проекты. Корневой `tsconfig.json` направляет редактор в Nuxt-конфигурацию, а workspace-настройки исключают служебные файлы из отдельной индексации.

Если редактор показывает ошибки внутри `.nuxt/*.d.ts`, хотя `npm run typecheck` проходит:

```bash
npm run prepare:nuxt
```

Затем выполните в VS Code команды `TypeScript: Select TypeScript Version` → `Use Workspace Version` и `Developer: Reload Window`.
