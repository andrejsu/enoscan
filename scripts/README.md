# Scripts

## Датасет и окружение

Импорт каталога и картинок выполняет сервис `services/importer`, а не скрипты из этой папки.

- `dev-entrypoint.sh`, `dev-shell.sh` — entrypoint и shell dev-контейнера `web`.

## Оценка поиска по фото

- `eval_ranking.py` — оценка сканера по критериям ТЗ: размеченные фото (`configs/labeled-photos.tsv`) отправляются в `ranking /v1/eval/predict` как в `participant_test.sh` и в `/v1/search` за top-5 и отрывом. Считает долю совпадений, precision/recall/F1 для top-1 и top-5, отрыв top-1 от top-2 для верных и ошибочных ответов, задержки и долю в SLA 3 с; пишет `predictions.jsonl` в формате организатора. `--predictions` оценивает готовый выход официального скрипта, сопоставляя фото по SHA-256. Без зависимостей.
- `eval_search.py` — оценка старого `SearchService` (визуальный SIFT, сервис `retrieval`), не продуктового сканера. Синтетика не равна точности на реальных фото.
- `smoke_search.py` — HTTP smoke контракта retrieval API.
- `eval.py`, `eval_augmentations.py` — старая синтетическая оценка только `SiftIndex` на аугментациях эталонов.
- `audit_mapping.py` — аудит привязки фото к винам: читает привязку из PostgreSQL, картинки из MinIO и сравнивает эмбеддинги. Пишет `reports/mapping_audit_<дата>.json` и `reports/image-overrides-proposed.csv` в формате `db/image-overrides.csv`. Предложения не применяются автоматически: проверьте строки и перенесите нужные в `db/image-overrides.csv`, после чего выполните `docker compose up -d`.
- `eval.py`, `eval_search.py` берут текущий SIFT-индекс и эталонные картинки из MinIO; аргументы `--index` и `--dataset` больше не нужны.
- `label_prep.py` — подготовка эталонов для экспериментального retriever (`docs/2b_RETRIEVER.md`).

Сырые JSON-результаты пишутся в `reports/` и не коммитятся; в git остаются только сводки.

## Сомелье

- `eval-sommelier.ts` — русский red-team набор против запущенного сервера (`npm run eval:sommelier`).
