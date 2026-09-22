# Ретривер винных этикеток (standalone, отключён от основного сканера)

Статус на 2026-09-22: код в репозитории, полностью рабочий и протестированный,
**но нигде не подключён**. `apps/web` (основной сканер) ходит в сервис
`retrieval` (`app/main.py` + `app/service.py`) — это не менялось и не
затрагивалось ничем из описанного ниже. Ретривер — параллельная, независимая
ветка кода на случай, если его решат подключить к «главному пайплайну» позже.

## Зачем он вообще есть

Основной сканер (`retrieval`) — это SIFT + FLANN + OCR (Tesseract) +
текстовый поиск по названию/винодельне. Ретривер — принципиально другой,
чисто визуальный подход: эмбеддинг этикетки (DINOv2) + ANN-поиск по векторам
+ SIFT/RANSAC геометрическая проверка. Он не читает текст с этикетки вообще
и не знает о существовании `app/ocr.py`/`app/text_search.py` — это разные
инструменты, каждый может использоваться отдельно.

## Архитектура

```
фото → label_normalize.prepare_query()      # кроп + normalize, БЕЗ SAM по умолчанию
     → embedding.Dinov2Encoder               # 384-мерный вектор
     → retriever_index.RetrieverIndex
         .embedding_scores()                 # косинусная близость ко всем референсам
         .search()                           # SIFT/FLANN голосование + шортлист
     → retriever.VisualRetriever             # объединяет оба источника кандидатов,
                                              # SIFT+RANSAC верификация каждого,
                                              # комбинированный скор:
                                              # 0.45·SIFT + 0.55·embedding
     → топ-10 кандидатов, по убыванию скора
```

Файлы:

| Файл | Роль |
|---|---|
| `app/retriever.py` | `VisualRetriever` — вся логика ранжирования, ни одного импорта из `ocr.py`/`text_search.py`/`service.py` |
| `app/retriever_index.py` | `RetrieverIndex` — свой SIFT+FLANN+embeddings индекс, отдельный от `app/index.py` (`SiftIndex`, которым пользуется основной сканер) |
| `app/retriever_main.py` | Отдельное FastAPI-приложение (`/health`, `/v1/search`, `/v1/wines/{slug}/image`) |
| `app/retriever_config.py` | Настройки, свои переменные окружения, не пересекаются с `app/config.py` |
| `app/build_retriever_index.py` | Сборка индекса `retriever-v1.npz` из каталога БД |
| `app/label_normalize.py` | Обёртка над `scripts/label_prep.py` — нормализация и для запроса, и для референсов |
| `app/embedding.py` | DINOv2 ONNX энкодер |
| `Dockerfile.retriever` | Отдельный образ (контекст — корень репо, нужен `scripts/label_prep.py`) |
| `tests/tune_weights_experiment.py` | Разовый скрипт калибровки весов (не часть тестов, не попадает в образ) |

## Как поднять отдельно (не трогая основной стек)

```bash
docker compose up retriever-model     # разово: скачивает DINOv2 + SAM модели
docker compose up retriever-index     # разово: строит /indexes/retriever-v1.npz из каталога БД (~15-20 мин на 2098 вин, без SAM)
docker compose up -d retriever        # сервис на порту 8081
```

`web` эти сервисы не запускает автоматически (`depends_on` на них нет) —
поднимать нужно явно.

## API

### `POST /v1/search` — как вызвать

Запрос — `multipart/form-data`, одно поле `image` (файл JPEG/PNG/WebP, до 10 МБ):

```bash
curl -X POST http://127.0.0.1:8081/v1/search \
  -F "image=@bottle_photo.jpg;type=image/jpeg"
```

Код на своей стороне:
1. Отправить фото как есть — никакой предобработки на клиенте не нужно, всю нормализацию (кроп, при необходимости — цвет/резкость) делает сам сервис.
2. Проверить `status`:
   - `"matched"` — уверенно, `wine` заполнен, можно сразу показывать карточку.
   - `"uncertain"` — топ-кандидат похож, но неуверенно; `wine` = `null`, предложить пользователю выбрать из `candidates`/`alternatives` (там же лежит текст `guidance` — что улучшить в кадре).
   - `"not_found"` — совпадения нет; `wine` = `null`, `candidates` может быть пустым.
3. Если нужен список вариантов (не только топ-1) — брать `candidates` целиком, он уже отсортирован по убыванию `score`/`confidencePercent`.

### Ответ — контракт полей

Форма ответа — тот же `ScanResponse` из `packages/contracts`, что отдаёт основной сканер (можно переиспользовать TS-тип), но с отличиями:
- `candidates` — ровно **10** элементов (если в индексе меньше подходящих — может быть короче), у каждого: `slug` (string), `score` (0..1), `confidencePercent` (0..100, `round(score*100)`), `wine` (карточка вина или `null`, если у кандидата нет привязанного фото в каталоге)
- `confidence.kind` всегда `"similarity"` — это НЕ калиброванная вероятность, просто нормализованный скор ретривера; не показывать пользователю как «% того, что это точно то вино»
- `version.model: "retriever-sift-dinov2-v1"` — по этому полю отличать ответ ретривера от основного сканера (`"sift-ransac-text-v2"`), если оба когда-нибудь окажутся за одним фронтом

```json
{
  "status": "matched | uncertain | not_found",
  "wine": { "slug": "...", "name": "...", "producer": "...", "imageUrl": "..." } | null,
  "candidates": [
    {"slug": "...", "score": 0.62, "confidencePercent": 62, "wine": {...} | null},
    ...  // до 10, по убыванию score
  ],
  "confidence": {"kind": "similarity", "top1Score": 0.62, "top1Percent": 62, "margin": 0.13},
  "timing": {"totalMs": 1400, "stages": {"normalizeMs": ..., "embeddingMs": ..., "featuresMs": ..., "searchMs": ...}},
  "alternatives": [ ... ],  // candidates[1:10] как WineCard, без скора — то же самое, что и в candidates, но в формате карточки
  "version": {"model": "retriever-sift-dinov2-v1", "catalog": "dataset-v1", "configuration": "..."},
  "guidance": "..." ,       // только при status != "matched"
  "isMock": false
}
```

### Ошибки

| Код | Когда | `detail` |
|---|---|---|
| `400` | пустое тело / нет файла в поле `image` | «Добавьте фотографию в поле image.» |
| `413` | файл больше 10 МБ | «Размер фотографии не должен превышать 10 МБ.» |
| `415` | не JPEG/PNG/WebP (`Content-Type` вне списка) | «Поддерживаются JPEG, PNG и WebP.» |
| `422` | файл не декодируется как изображение (битый/не картинка) | текст ошибки декодера |
| `503` | индекс/модели ещё не загрузились после старта контейнера | «Индекс ретривера ещё загружается.» — стоит retry через пару секунд |

Формат ошибки — стандартный FastAPI: `{"detail": "..."}`.

### `GET /v1/wines/{slug}/image`

Картинка референса из каталога (та, что уже лежит в `candidates[].wine.imageUrl`/`wine.imageUrl` как относительная ссылка). `404`, если слага нет в индексе или файла нет на диске.

### `GET /health`

`{"status": "ok"}` когда индекс и модели загружены, `{"status": "loading"}` — до этого (сразу после старта контейнера, пока идёт загрузка `.npz`+ONNX). Использовать для healthcheck/retry-логики при поднятии сервиса.

## Конфигурация (`retriever_config.py`, все опциональны)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `RETRIEVER_INDEX_PATH` | `/indexes/retriever-v1.npz` | путь к индексу |
| `MODEL_PATH` | `/models/dinov2-small.onnx` | DINOv2 ONNX |
| `SAM_MODEL_DIR` | `/models/sam_vit_b_quant` | SAM (только если `QUERY_SAM=true`) |
| `VISUAL_SHORTLIST_LIMIT` | `24` | сколько кандидатов даёт SIFT/FLANN-голосование до RANSAC-проверки |
| `EMBEDDING_SHORTLIST_LIMIT` | `20` | сколько кандидатов даёт ANN по эмбеддингу |
| `QUERY_SAM` | `false` | `true` включает полную SAM-нормализацию запроса (развёртка цилиндра, деskew) — точнее, но **+8-17с** на запрос вместо ~0.4с. Выключено по умолчанию ради бюджета ~1.5-2с на поиск |

## Точность на реальных фото (6 фикстур, `tests/fixtures/`)

**4 из 6** верных топ-1 со статусом `matched` (уверенно): balaklava-muskat,
abrau-dyurso, yaiyla-kokur, zakat-denisov-vajneri.

**2 промаха, оба честно остаются `uncertain`, не ложно-уверенные:**
- `perovskih_polusuhoe_krasnoe` — референс в каталоге привязан к чужому
  стоковому фото (баг `fuzzy_filename`-маппинга в `catalog.py`, не в
  ретривере — см. `resolve_references`)
- `zhemchuzhnaya-9-aligote-czitron` — соседнее вино той же линейки
  (`zhemchuzhnaya-9-czitron-shardone`) визуально почти неотличимо; отличаются
  сортом винограда в тексте на этикетке. Без OCR это принципиально не
  решить — ретривер по требованию отделён от текстового поиска.

Веса скоринга (`SIFT_WEIGHT=0.45`, `EMBEDDING_WEIGHT=0.55` в `retriever.py`)
и порог `margin>=0.015` для статуса `matched` (в `retriever_main.py`)
откалиброваны на этих 6 фото методом `tests/tune_weights_experiment.py` —
стабильное плато 0.30-0.55 по весу SIFT, а не подгонка под одно значение, но
выборка маленькая. Пересчитать на большей выборке, когда она появится.

## Производительность

Без SAM (`QUERY_SAM=false`, по умолчанию): **~1.2-2с** на поиск, память
контейнера ~2.2-2.4 ГБ в простое (индекс на 2098 вин + FLANN-структура +
DINOv2). С `QUERY_SAM=true`: точнее на сильно наклонённых/изогнутых фото, но
+8-17с — тестировалось отдельно, для боевого пути пока не годится.

## Если понадобится снова подключить к сканеру

Временная связка (уже опробована и откачена) была: в `apps/web/nuxt.config.ts`
добавить `retrieverBaseUrl`, в `apps/web/server/api/scans.post.ts` дёргать
его вместо `retrievalBaseUrl`, в `compose.yaml` — `NUXT_RETRIEVER_BASE_URL` и
`depends_on: retriever` у сервиса `web`. Сознательно всё это отсутствует в
текущем коде — подключать нужно осознанно, а не как побочный эффект правки
ретривера.
