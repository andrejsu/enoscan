## Быстрый старт

Требования: Node.js 22.22.2+ и npm 10+. Версия зафиксирована в `.nvmrc`.

```bash
nvm use
npm install
npm run dev
```

После запуска откройте `http://localhost:3000`. При запуске без Docker маршрут остаётся в демонстрационном mock-режиме; полный Compose-стек подключает локальное распознавание.

Астро-сомелье управляется публичным runtime-флагом `NUXT_PUBLIC_ASTRO_ENABLED`. Значение `false` скрывает пункт меню и блок знака вина, перенаправляет страницу функции на главную и закрывает её API ответом `404`. После изменения `.env` пересоздайте web-контейнер: `docker compose up -d --force-recreate web`. Пересборка образа не требуется.

Read-only админка каталога доступна на `http://localhost:3000/admin`. Она показывает сводку по PostgreSQL и медиа, позволяет искать по названию, производителю, slug и региону, фильтровать карточки по наличию изображения в поисковом индексе и раскрывать исходные поля и диагностику привязки файла.

## Цифровой сомелье

Страница `http://localhost:3000/sommelier` ведёт диалог о выборе вина к блюду, событию или вкусовому профилю. По умолчанию работает маркированный `mock`-режим: он не отправляет данные внешнему AI и не выдаёт демонстрационные карточки за живой поиск. История хранится только в `localStorage` браузера.

Режим задаётся через `NUXT_PUBLIC_SOMMELIER_MODE`:

- `mock` — воспроизводимые ответы без ключа и PostgreSQL;
- `live` — server-side AI и обязательный поиск по `wine_catalog`;
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

Поместите `prod-svoe-vino-strapi.part1.rar`, `prod-svoe-vino-strapi.part2.rar`, `prod-svoe-vino-strapi.part3.rar`, `strapi_output0709.csv` и `eval.zip` в `data/dataset/`. Для сборки и входа:

```bash
docker compose up --build -d
docker compose exec web sh
```

Первый запуск дополнительно строит SIFT-индекс эталонных этикеток и поэтому занимает больше времени. Следующие запуски используют постоянный volume `vinolog_retrieval-index`. API проверки доступен на `http://localhost:8080/v1/eval/predict`.

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

Первый запуск распаковывает медиа Strapi, CSV-каталог и проверочный набор в постоянный том `vinolog_dataset`. Следующие запуски используют этот том без повторной распаковки, в том числе после `docker compose down` и пересборки образа. В контейнере данные доступны только для чтения по пути `/workspace/Vinolog/data/installed/current/{uploads,catalog,eval}`. Локальный каталог `data/dataset/` подключается к контейнеру инициализации только для чтения и исключен из build context. В Compose приложение отправляет фотографию в локальный retrieval-сервис, который ищет кандидатов по визуальным признакам этикетки и возвращает карточку из PostgreSQL.

При первом `docker compose up` создаётся PostgreSQL и загружается весь CSV в `wine_catalog_raw` без удаления дублей. Представление `wine_catalog` даёт одну запись на `slug`; `wine_media` содержит пути и размеры файлов из всех частей RAR, а сами изображения остаются в `vinolog_dataset`. Таблица `dataset_imports` фиксирует импорт и хеш CSV. БД сохраняется в томе `vinolog_postgres-data` и не загружается повторно при следующих запусках. Внутри web-контейнера `psql` уже настроен через `PGHOST`/`PGUSER`/`PGDATABASE`:

```bash
psql -c 'SELECT catalog_rows, media_rows FROM dataset_imports;'
psql -c 'SELECT slug, name, winery FROM wine_catalog LIMIT 5;'
```

С хоста PostgreSQL доступен на `localhost:5433` (порт меняется через `VINLOG_DB_PORT` в `.env`). Локальный пользователь и БД — `vinolog`, пароль — `VINLOG_DB_PASSWORD` из `.env` или `vinolog` по умолчанию. Изображение с путём `relative_path` из `wine_media` находится под `data/installed/current/uploads/` внутри web. Имена фото в CSV связываются с оригиналами Strapi по исходному имени, `slug` и только затем по консервативному сходству токенов имени. Неуверенные связи не попадают в индекс. Docker собирает образы командой `build`, а БД создаёт и импортирует данные при первом `up`; SQL-дампа в наборе нет.

После изменения исходников пересборка не требуется; изменение Dockerfile или Compose примените командой `docker compose up --build -d`. Локальный `.env` необязателен и игнорируется Git. Для намеренного повторного импорта обновлённого набора удалите только его тома после `docker compose down`: `docker volume rm vinolog_dataset vinolog_postgres-data vinolog_retrieval-index`. Эта команда удаляет локальные распакованные данные, БД и производный индекс, но не исходные архивы. `.env`, `models/` и `indexes/` также исключены из образа.

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
- `packages/contracts` — общие TypeScript-контракты без зависимости от Nuxt.
- `services/retrieval` — локальный Python/FastAPI-сервис поиска по этикетке.
- `docs/engineering` — обязательные правила генерации и изменения кода.
- `ARCHITECTURE.md` — компоненты системы и поток запроса.

## Текущее ограничение

Compose закрывает путь от фото до карточки и официальный маршрут оценки. SIFT/RANSAC объединяется с текстовым поиском по полному каталогу; Tesseract остаётся OCR по умолчанию. Реализованы структурированное извлечение, мягкая проверка года, timeout/fallback и ручной выбор кандидата. Пороги остаются эвристическими, точность на размеченных полевых фотографиях не измерена. Для цифрового сомелье реализованы три провайдерских адаптера, но live-качество, стоимость и русский red-team набор ещё не прогнаны с реальными ключами каждого провайдера; mock-тесты не доказывают поведение внешних моделей.

### Оценка полного поиска с OCR

`scripts/eval.py` проверяет только визуальный индекс. `scripts/eval_search.py` проверяет SearchService и сохраняет прогноз каждого запроса, ошибки, версии, Accuracy@1, Recall@5, охват/точность автоматических ответов и задержки. Для текущего локального Docker-образа:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace retrieval \
  python scripts/eval_search.py --index /indexes/sift-v2.npz \
  --dataset /dataset/current --synthetic 8 --profile hard \
  --label synthetic-default --output reports/photo-search-local.json
```

Этот режим использует только каталог индекса и искажённые эталоны. Для полного каталога добавьте `--full-catalog` при работающей БД. Для доступных трёх неразмеченных фото вместо `--synthetic 8 --profile hard` укажите `--manifest configs/photo-search-pilot.jsonl --split pilot`. У них намеренно отсутствует `expected_slug`: точность для них не рассчитывается.

Собственный manifest — JSONL, пути относительно manifest либо абсолютные:

```json
{"path":"photos/one.jpg","expected_slug":"actual-catalog-slug","group":"capture-session-1","split":"tuning","expected_year":2019,"expected_abv":12.5}
{"path":"photos/unknown.jpg","expected_slug":null,"group":"capture-session-2","split":"holdout"}
```

`expected_slug: null` означает проверенное неизвестное вино; отсутствие ключа — отсутствие разметки. Одна съёмка не может попадать в разные split. Не угадывайте правильные ответы по прогнозу модели. Поля `expected_year`/`expected_abv` необязательны; `null` означает, что извлечение должно воздержаться. Параметры эксперимента: `--psm 11`, `--raw`, `--retry`, `--ocr-timeout 2`. В сервисе соответствуют `OCR_PSM`, `OCR_PREPROCESS`, `OCR_RETRY`, `OCR_TIMEOUT_SECONDS`; передавайте их через окружение контейнера. По умолчанию альтернативные проходы отключены.

HTTP-проверка доступных фото и ошибочных загрузок:

```bash
python3 scripts/smoke_search.py --base http://127.0.0.1:8080 \
  --output reports/photo-search-http-local.json
```

Она проверяет одинаковый top-1 продуктового/оценочного маршрутов, формат и HTTP-ошибки, но не правильность найденного вина. Python-тесты сервиса и оценочного скрипта:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace/services/retrieval retrieval \
  python -m pytest services/retrieval/tests scripts/tests -q -p no:cacheprovider
```

## Диагностика TypeScript в редакторе

Папки `.nuxt` и `.output` генерируются фреймворком и не проверяются как самостоятельные TypeScript-проекты. Корневой `tsconfig.json` направляет редактор в Nuxt-конфигурацию, а workspace-настройки исключают служебные файлы из отдельной индексации.

Если редактор показывает ошибки внутри `.nuxt/*.d.ts`, хотя `npm run typecheck` проходит:

```bash
npm run prepare:nuxt
```

Затем выполните в VS Code команды `TypeScript: Select TypeScript Version` → `Use Workspace Version` и `Developer: Reload Window`.
