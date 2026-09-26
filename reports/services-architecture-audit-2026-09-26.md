# План архитектурного улучшения `services`

Дата: 2026-09-26  
Область: код `services/retrieval` и `services/importer`.  
Не входит в приоритет: production Compose, deployment и эксплуатационная конфигурация.

## Итоговое направление

Главное улучшение — не просто разложить файлы по папкам, а собрать актуальный сценарий сканирования в один глубокий модуль `search` с малым интерфейсом:

```python
result = await search_service.scan(image)
```

Внутри этого модуля должны остаться скрыты:

- параллельный вызов OCR и visual retriever;
- обработка отказа одного источника;
- преобразование ответов источников в единый evidence contract;
- ranking, verification и recommendations;
- выбор `matched` / `uncertain` / `not_found`;
- timings и версии алгоритмов.

FastAPI route должен только проверить upload, вызвать `SearchService` и преобразовать результат в HTTP response. OCR и visual retriever должны отдавать evidence, а не самостоятельно решать, найдено ли вино.

Вторая часть улучшения — сделать структуру пакета соответствующей реальным capabilities:

```text
ocr/       распознаёт текст и поля этикетки
visual/    получает visual-кандидатов
search/    объединяет evidence и принимает продуктовое решение
baseline/  изолированный legacy SIFT benchmark либо удаляется
catalog/   модель каталога и PostgreSQL adapter
```

Разносить эти части по отдельным repository packages и Docker build contexts сейчас не нужно. Это добавит packaging shared-кода, но не улучшит интерфейсы модулей.

## Главные архитектурные проблемы

### P0. Актуального продуктового `SearchService` фактически нет

Название `SearchService` сейчас занято legacy SIFT baseline ([`service.py:24`](../services/retrieval/app/service.py#L24)). Актуальный сценарий находится в `_scan`, module globals, response assembly и debug внутри [`ranking_main.py`](../services/retrieval/app/ranking_main.py).

Из-за этого:

- route одновременно является composition root, orchestrator и presenter;
- тесты patch-ят private `_post_image`, а не проверяют продуктовый интерфейс ([`test_ranking_main.py`](../services/retrieval/tests/test_ranking_main.py));
- transport DTO, domain evidence и HTTP response смешаны;
- переиспользовать сценарий без FastAPI сложно;
- имя `SearchService` указывает на неправильный, уже не продуктовый код.

Решение: создать `app/search/service.py` с одним публичным методом `scan`. Зависимости передавать в конструктор:

```python
class SearchService:
    def __init__(
        self,
        ocr: OcrEvidencePort,
        visual: VisualEvidencePort,
        wines: Sequence[Wine],
        settings: SearchSettings,
    ) -> None: ...

    async def scan(self, image: ScanImage) -> ScanResult: ...
```

`SearchService` — внешний seam модуля. `rank`, verification, recommendations и concurrent calls являются implementation detail и не должны вызываться route/test-кодом по отдельности.

### P0. Межмодульный evidence contract — это не типизированный интерфейс

Ranking получает OCR и visual как `dict | None`, читает строковые ключи и вручную строит `RetrievalFields` ([`ranking_main.py:88`](../services/retrieval/app/ranking_main.py#L88), [`ranking_main.py:134`](../services/retrieval/app/ranking_main.py#L134)). `fields_from_json` также принимает нетипизированный `dict` ([`label_fields.py:42`](../services/retrieval/app/label_fields.py#L42)).

Нужно разделить три формы данных:

1. **Wire DTO** — Pydantic models ответа OCR/visual HTTP.
2. **Domain evidence** — immutable dataclasses `FieldCandidate`, `RetrievalFields`, `VisualCandidate`.
3. **Product result** — `ScanResult`, который затем отображается в `ScanResponse`.

Предлагаемые интерфейсы:

```python
class OcrEvidencePort(Protocol):
    async def retrieve(self, image: ScanImage) -> OcrEvidence: ...

class VisualEvidencePort(Protocol):
    async def retrieve(self, image: ScanImage) -> VisualEvidence: ...
```

HTTP adapters реализуют эти интерфейсы и только там знают про `httpx`, URL, multipart, timeout и Pydantic parsing. В тестах используются in-memory adapters. Это реальный seam: production и test implementations уже существуют, сейчас они просто выражены через patch функции.

Не нужно создавать Protocol для `rank`, `Wine` или каждой repository-функции: там нет реальной вариативности.

### P0. Visual retriever принимает лишнее продуктовое решение

[`retriever_main.py`](../services/retrieval/app/retriever_main.py) вычисляет собственный `matched/uncertain/not_found`, guidance, cards и alternatives, хотя актуальный search использует только `candidates` ([`ranking_main.py:134`](../services/retrieval/app/ranking_main.py#L134)). Те же пороги частично дублируются в legacy [`service.py`](../services/retrieval/app/service.py).

Visual module должен иметь узкий интерфейс:

```text
VisualEvidence
  candidates[]
    slug
    score
    good_matches
    inliers
  timing
  model/index version
```

Из visual response следует удалить:

- product status;
- `wine` и `alternatives`;
- guidance;
- product confidence/margin;
- `confidencePercent` и `top1Percent`.

Последние два поля также нарушают прямое правило не превращать similarity в проценты ([`CODE_RULES.md:43`](../docs/engineering/CODE_RULES.md#L43)). Единственное место продуктового решения — `SearchService`.

Контракт при этом объявляет три статуса, а текущий `rank()` фактически возвращает только `matched` или `not_found` ([`ranking.py:280`](../services/retrieval/app/ranking.py#L280)). Во время архитектурного переноса это поведение нужно сначала сохранить. Возврат `uncertain` либо его удаление из shared contract — отдельное продуктовое изменение, которое не следует смешивать с реорганизацией модулей.

### P1. Структура корня `app/` скрывает реальные modules

Сейчас рядом лежат файлы четырёх разных capabilities:

```text
main.py, service.py, index.py              legacy baseline
retriever_main.py, retriever.py, ...       current visual
ocr/                                       OCR
ranking_main.py, ranking.py, ...           product search
catalog.py                                 model + DB + serializers
```

OCR уже показывает полезный уровень группировки. Такой же уровень нужен visual и search. Папки создаются по capability, а не по техническому типу: не должно быть общих `models/`, `services/`, `repositories/` на весь проект.

Целевая структура:

```text
services/retrieval/app/
  common/
    upload.py
    settings.py

  catalog/
    models.py
    repository.py

  label_text/
    tokens.py
    facts.py
    sweetness.py

  evidence.py

  ocr/
    api.py
    service.py
    engine.py
    vocabulary.py
    fields.py
    constants.py
    schemas.py

  visual/
    api.py
    service.py
    index.py
    embedding.py
    embedding_store.py
    preprocessing.py
    build_index.py
    config.py
    schemas.py

  search/
    api.py
    service.py
    ports.py
    http_adapters.py
    ranking.py
    verification.py
    recommendations.py
    debug.py
    config.py
    schemas.py

  baseline/                 # только если benchmark решено сохранить
    api.py
    service.py
    index.py
    build_index.py
    config.py

  index_store.py
  storage.py
```

`evidence.py` остаётся маленьким shared domain contract между OCR, visual и search. Он не должен импортировать FastAPI, httpx, PostgreSQL или OpenCV.

`storage.py` и `index_store.py` пока можно оставить в корне: ими пользуются visual и baseline. Создавать ради двух файлов абстрактный `infrastructure/` необязательно.

### P1. Точные перемещения файлов

| Сейчас | Целевое место | Примечание |
|---|---|---|
| `ranking_main.py` | `search/api.py` | только FastAPI/composition root |
| `ranking.py` | `search/ranking.py` + `search/verification.py` | разделить scoring и label verification, сохранить один публичный `rank` |
| `ranking_config.py` | `search/config.py` | только настройки search |
| `ranking_schemas.py` | `search/schemas.py` | HTTP response models |
| `recommendations.py` | `search/recommendations.py` | internal search behavior |
| `scan_debug.py` | `search/debug.py` | presenter debug trace |
| `retriever_main.py` | `visual/api.py` | тонкий producer route |
| `retriever.py` | `visual/service.py` | `VisualRetriever` |
| `retriever_index.py` | `visual/index.py` | current index implementation |
| `embedding*.py` | `visual/` | visual-only dependencies |
| `label_normalize.py` | `visual/preprocessing.py` | visual preparation; OCR-specific crop остаётся в OCR |
| `build_retriever_index.py` | `visual/build_index.py` | current builder |
| `retriever_config.py` | `visual/config.py` | visual settings |
| `label_fields.py` | `evidence.py` | shared immutable domain evidence |
| `catalog.py` | `catalog/models.py`, `catalog/repository.py` | transport/index serializers вынести к владельцам |
| `main.py`, `service.py`, `index.py`, `build_index.py`, `config.py` | `baseline/` или удалить | не смешивать с current path |

Перемещение папок должно быть отдельным механическим этапом после появления `SearchService`. Иначе большой import diff одновременно изменит структуру и поведение, что затруднит проверку.

### P1. Legacy baseline создаёт ложную архитектурную параллель

README прямо говорит, что `retrieval` не стоит за продуктовым и evaluation routes и нужен только старому benchmark ([`README.md:167`](../README.md#L167)). При этом legacy класс носит главное имя `SearchService`, а его SIFT index живёт рядом с current `RetrieverIndex`.

Нужно принять простое решение:

- если benchmark больше не используется — удалить legacy flow, связанные scripts и tests;
- если используется — перенести в `baseline/` и переименовать класс в `BaselineSearch`.

Не следует строить общую hierarchy над current и legacy search. Это разные назначения: один является продуктовым модулем, другой — измерительным baseline.

### P1. SIFT index продублирован почти полностью

[`index.py`](../services/retrieval/app/index.py) и [`retriever_index.py`](../services/retrieval/app/retriever_index.py) дублируют около 180 строк: модели, NPZ codec, FLANN shortlist, RANSAC rerank и score formula. Отличаются в основном числовые параметры и index kind.

Порядок решения:

1. Сначала решить судьбу baseline.
2. Если baseline удаляется — удалить duplication вместе с ним.
3. Если остаётся — один `SiftIndex` и immutable `SiftSearchConfig` с FLANN params, feature count и shortlist cap.

Наследование, abstract base index и strategy classes здесь избыточны: алгоритм один, меняются параметры.

### P1. Общая семантика текста ошибочно принадлежит OCR

`search`-код импортирует `ocr.constants`, `ocr.fields` и `ocr.tokens` ([`ranking.py:40`](../services/retrieval/app/ranking.py#L40), [`recommendations.py:26`](../services/retrieval/app/recommendations.py#L26)). `_long_tokens` продублирован в ranking и recommendations.

Tokenization, fuzzy token comparison, year/sweetness facts используются не только OCR engine. Их владелец — общий чистый модуль `label_text/`:

- `tokens.py`: normalization, tokenization, token similarity;
- `facts.py`: извлечение year/ABV и другие чистые label facts;
- `sweetness.py`: единый разбор сахара.

В `ocr/` остаются:

- загрузка RapidOCR;
- `OcrWord`/`OcrResult`;
- crop/fallback passes;
- vocabulary search и преобразование OCR output в evidence.

Не создавать `utils.py`: он быстро вернёт текущую проблему плоского корня под другим именем.

### P2. `catalog.py` смешивает четыре ответственности

`Wine` является domain model, строит web card, сериализуется в NPZ и предоставляет dynamic `field_values`; в том же файле находятся PostgreSQL queries ([`catalog.py:18`](../services/retrieval/app/catalog.py#L18), [`catalog.py:31`](../services/retrieval/app/catalog.py#L31), [`catalog.py:55`](../services/retrieval/app/catalog.py#L55), [`catalog.py:98`](../services/retrieval/app/catalog.py#L98)).

Разделение:

- `catalog/models.py`: `Wine`, `Reference`, domain-only methods;
- `catalog/repository.py`: `current_dataset_version`, `load_wines`, `load_references`;
- mapping `Wine -> WineCard`: `search/schemas.py` или `search/api.py`;
- `Wine <-> NPZ JSON`: `visual/index.py`.

Generic repository interface не нужен: сейчас существует один PostgreSQL adapter. Простые функции здесь KISS и достаточны.

### P2. `importer/run.py` объединяет сценарий импорта и SQL writer

В целом importer структурирован лучше retrieval: parsing, archive, mapping, overrides и image processing уже разделены. Узкое место — `write_catalog_state`, которое одновременно выполняет upsert каталога, деактивацию, mapping, overrides, полную замену `wine_images`, запись issues и расчёт stats ([`run.py:194`](../services/importer/importer/run.py#L194)).

Улучшение:

- оставить `run.py` composition root и владельцем transaction boundary;
- перенести persistence operations в `catalog_writer.py` обычными функциями;
- оставить mapping/overrides чистыми и не прятать их внутрь repository;
- описать object storage минимальным `Protocol`: boto adapter и тестовый `MemoryStore` уже являются двумя реальными реализациями seam.

Не нужно дробить importer на новые процессы или классы с одним методом на каждый SQL statement.

## Кандидаты на удаление

Проверка выполнена по Python AST, точным ссылкам во всём исполняемом коде,
тестам, scripts, Dockerfile и Compose entrypoints. Ссылки только из
исторических Markdown-планов не считались runtime-использованием.

### Подтверждённый dead code

- [ ] **delete:** удалить разовый
  [`tests/tune_weights_experiment.py`](../services/retrieval/tests/tune_weights_experiment.py):
  файл не соответствует pytest naming, не импортируется, не копируется в
  runtime image и упоминается только в исторических `thoughts`; результаты
  калибровки уже зафиксированы в документации. Replacement: nothing.
- [ ] **delete:** удалить `read_embedding_image()`
  ([`embedding.py:28`](../services/retrieval/app/embedding.py#L28)): в
  репозитории нет ни одного caller; current builder декодирует изображение
  через `decode_reference_unchanged()`. Replacement: nothing.
- [ ] **delete:** удалить неиспользуемые методы importer
  `ObjectStore.put_file`, `get_bytes`, `delete_prefix`
  ([`storage.py:43`](../services/importer/importer/storage.py#L43)): importer
  использует только `ensure_bucket`, `exists`, `put_bytes` и
  `list_keys`; тестовый `MemoryStore` также не реализует удаляемые методы.
  Replacement: nothing.
- [ ] **delete:** удалить `RetrievalResult.ocr_image`, `used_sam` и
  `warnings` вместе с их заполнением
  ([`retriever.py:33`](../services/retrieval/app/retriever.py#L33),
  [`retriever.py:104`](../services/retrieval/app/retriever.py#L104)):
  ни route, ни ranking, ни tests не читают эти поля. Debug получает
  `used_sam/warnings` из собственного вызова `prepare_query`.
- [ ] **delete:** после предыдущего пункта удалить
  `PreparedQuery.ocr` и лишнюю OCR-ветку возврата из visual preprocessing
  ([`label_normalize.py:51`](../services/retrieval/app/label_normalize.py#L51)):
  сейчас поле только перекладывается в неиспользуемый
  `RetrievalResult.ocr_image`. OCR service использует собственный crop и не
  читает `PreparedQuery.ocr`.
- [ ] **delete:** удалить `RetrieverIndex.SearchResult.visual_slugs` и его
  вычисление
  ([`retriever_index.py:45`](../services/retrieval/app/retriever_index.py#L45),
  [`retriever_index.py:114`](../services/retrieval/app/retriever_index.py#L114)):
  current visual flow читает только candidates и timings. Не путать с таким
  же полем legacy `index.py`: там оно используется
  `scripts/eval_search.py`.
- [ ] **delete:** удалить `Candidate.image_sha256` из обоих SIFT result
  models ([`index.py:26`](../services/retrieval/app/index.py#L26),
  [`retriever_index.py:36`](../services/retrieval/app/retriever_index.py#L36)):
  значение передаётся в каждый candidate, но ни один consumer его не читает.
  `IndexedReference.image_sha256` при этом оставить — оно используется
  builder/index registry и embedding shortlist.
- [ ] **delete:** удалить `mapping_kind` и `mapping_score` из
  `index.IndexedReference` и `retriever_index.IndexedReference`, а также
  из NPZ serialization
  ([`retriever_index.py:28`](../services/retrieval/app/retriever_index.py#L28),
  [`retriever_index.py:173`](../services/retrieval/app/retriever_index.py#L173)):
  metadata записывается и загружается, но search её нигде не читает.
  Mapping audit берёт эти значения напрямую из PostgreSQL через
  `catalog.Reference`, а не из индекса.
- [ ] **delete:** убрать `kind` и `dataset_version` из возвращаемого
  `IndexBuild`
  ([`index_store.py:11`](../services/retrieval/app/index_store.py#L11)):
  callers читают только `id`, `object_key` и `reference_count`; kind и
  version уже известны аргументам `find_build/register_build`.

### Не dead code, но лишний интерфейс

- [ ] **yagni:** удалить параметр `extra_slugs` и связанную ветку только из
  legacy `SiftIndex.search`
  ([`index.py:82`](../services/retrieval/app/index.py#L82)): ни один legacy
  caller его не передаёт. В current `RetrieverIndex` параметр оставить — он
  объединяет embedding shortlist с SIFT shortlist.
- [ ] **shrink:** удалить test-only wrapper `OcrRetriever.extract()`
  ([`ocr/retriever.py:53`](../services/retrieval/app/ocr/retriever.py#L53))
  и в `test_ocr_real.py` читать `retriever.trace(...).fields`: runtime
  использует только `trace`, отдельного второго интерфейса модулю не нужно.

### Удалять только вместе с архитектурным изменением

- [ ] **delete:** product status, wine cards, alternatives, guidance,
  `confidencePercent` и `top1Percent` из
  [`retriever_main.py`](../services/retrieval/app/retriever_main.py) после
  перехода ranking на типизированный `VisualEvidence`. Внутри репозитория
  ranking читает только `candidates`, но перед удалением нужно зафиксировать,
  что прямой HTTP endpoint visual retriever не является отдельным внешним
  контрактом.
- [ ] **delete:** legacy baseline package целиком только если принято решение
  отказаться от benchmark. Сейчас он **не dead code**: его используют
  `scripts/eval.py`, `scripts/eval_search.py`, тесты, Dockerfile и dev
  Compose. Удаление должно включать всех этих consumers, а не только файлы
  `main.py/service.py/index.py`.

### Ложные срабатывания статического анализа — не удалять

- FastAPI functions `product_search`, `search`,
  `evaluation_predict` и `health` вызываются через decorators.
- `main()` в builders/download scripts вызывается через
  `python -m ...`, Dockerfile или Compose.
- `download_sam.py` и `download_model.py` используются model image/build
  entrypoints.
- `sugar_levels()` вызывается через `sugar_level()`; это не dead helper.
- `OcrRetriever.extract()` не является полностью мёртвым: это test-only
  convenience wrapper, поэтому выше он помечен как `shrink`, а не
  подтверждённый runtime dead code.

**net: -200 lines, -0 dependencies possible (оценка после всех подтверждённых
удалений, включая разовый experiment-файл).**

## Направление зависимостей после рефакторинга

```text
search/api
    |
    v
SearchService ----------------------> catalog models
    |                                      ^
    +--> OcrEvidencePort                   |
    |      +--> HTTP OCR adapter --> ocr/api
    |
    +--> VisualEvidencePort
    |      +--> HTTP visual adapter --> visual/api
    |
    +--> ranking + verification + recommendations
                     |
                     v
                 label_text

ocr -------> evidence + catalog models + label_text
visual ----> evidence + catalog models + storage/index adapters
```

Запрещённые обратные зависимости:

- `ocr` и `visual` не импортируют `search`;
- domain ranking не импортирует FastAPI/httpx;
- `catalog/models.py` не импортирует PostgreSQL или response schemas;
- HTTP schemas не используются как domain models внутри ranking;
- `baseline` не импортируется current product path.

## DRY: что действительно объединять

Объединять:

- продуктовое решение и thresholds — только в `SearchService`/ranking;
- evidence DTO и их валидацию;
- два SIFT index, только если baseline остаётся;
- `_long_tokens` и общую label semantics;
- product response assembly для `/v1/search`;
- lifecycle state ranking-модуля в одном object вместо четырёх globals.

Не объединять:

- upload validation на разных network seams;
- settings OCR, visual и search — у процессов разные env contracts;
- importer `ObjectStore` и retrieval `ObjectStore` только из-за похожего boto setup: build contexts и требуемые операции различаются;
- importer filename normalization и OCR tokenization: назначения и допустимые ошибки разные;
- все dataclasses в глобальный `models.py`;
- все adapters в общий framework.

## KISS-ограничения для реализации

- Не добавлять dependency injection container; обычного конструктора `SearchService` достаточно.
- Не добавлять event bus, command handlers или use-case classes вокруг одного `scan`.
- Не делать generic `Repository[T]`.
- Не вводить base class для OCR/visual adapters; два маленьких `Protocol` яснее.
- Не разбивать `ranking.py` по числу строк. Выделить только scoring и verification, потому что у них разные причины изменения.
- Не форматировать весь Python-код одновременно с переносом файлов.
- Не менять веса, thresholds, OCR heuristics или evaluation behavior в архитектурных commits.

## Стилистика кода

После стабилизации структуры:

1. Добавить Ruff как один formatter/linter (`ruff format --check`, `ruff check`).
2. Сначала форматировать только затронутые архитектурным переносом модули; отдельный full-format commit допустим позже.
3. Использовать Pydantic на HTTP seams и dataclasses для pure domain values.
4. Убрать `dict`, `list[dict]`, `dict[str, object]` там, где структура является контрактом.
5. Оставить `dict[str, object]` только для действительно свободной debug-трассы.
6. После typed seams подключить один static type checker постепенно; не вводить одновременно mypy и Pyright.
7. Обновить устаревшие docstrings, называющие legacy flow OCR-driven scanner.

## Рекомендуемые этапы реализации

### Этап 1. Зафиксировать текущее поведение

- Добавить characterization tests для OCR-only, visual-only, согласия, конфликта и падения обоих sources.
- Добавить malformed producer payload и unknown slug.
- Сохранить проверку общего top-1 продуктового и evaluation routes.
- Не менять алгоритмы и пороги.

### Этап 2. Ввести typed evidence и adapters

- Добавить `evidence.py` с domain dataclasses.
- Добавить Pydantic wire schemas OCR/visual.
- Создать `OcrEvidencePort`, `VisualEvidencePort` и HTTP adapters.
- Перевести существующие route tests с patch `_post_image` на in-memory adapters.

### Этап 3. Создать глубокий `SearchService`

- Перенести `_scan`, degradation policy, ranking и recommendations за `scan(...)`.
- Убрать module globals из business flow; lifespan создаёт один service instance.
- Оставить `ranking_main.py` временным тонким shim, чтобы сократить diff.

### Этап 4. Упростить producer contracts

- Visual route отдаёт только evidence/timing/version.
- OCR route отдаёт типизированный evidence response.
- Product status, cards и guidance формируются только search-модулем.
- Удалить similarity percentages.

### Этап 5. Механически разложить capabilities по папкам

- `search/`, `visual/`, `catalog/`, `label_text/`.
- Исправить imports, Docker/Compose entrypoints и scripts.
- На этом этапе не менять implementation behavior.

### Этап 6. Разобраться с baseline и DRY

- Удалить либо изолировать `baseline/`.
- Только после решения объединить SIFT implementation, если остаются два callers.
- Удалить старые tests, которые проверяют implementation past нового интерфейса.

### Этап 7. Улучшить importer

- Вынести catalog persistence из `run.py`.
- Ввести storage `Protocol`.
- Сохранить существующий полный integration test через `run_import`.

### Этап 8. Поднять стиль

- Ruff;
- typed contracts;
- один static type checker по новым модулям;
- обновление README/ARCHITECTURE после финализации имён и путей.

## Первый практический срез

Самый полезный первый срез без большого file-move diff:

1. `app/evidence.py` — `FieldCandidate`, `RetrievalFields`, `OcrEvidence`, `VisualCandidate`, `VisualEvidence`.
2. `app/search/models.py` — `ScanImage` и `ScanResult`.
3. `app/search/ports.py` — два `Protocol`.
4. `app/search/http_adapters.py` — текущая логика `_post_image`, но с Pydantic validation.
5. `app/search/service.py` — текущая `_scan` и вызов `rank`.
6. `ranking_main.py` — только создаёт dependencies в lifespan и вызывает service.
7. `test_search_service.py` — tests через in-memory adapters.

После этого структура уже станет лучше даже до массового переноса файлов: появится настоящий интерфейс модуля, тестовая поверхность и место, куда последовательно переносить ranking-related implementation.

## Граница верификации

Сводка основана на текущих исходниках и тестах. Runtime и алгоритмы не изменялись; pytest/Docker не запускались, потому что этот этап остаётся архитектурным планом. Production-вопросы намеренно исключены из приоритетов по текущему решению.
