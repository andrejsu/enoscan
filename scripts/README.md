# Scripts

## Датасет и окружение

Импорт каталога и картинок выполняет сервис `services/importer`, а не скрипты из этой папки.

- `dev-entrypoint.sh`, `dev-shell.sh` — entrypoint и shell dev-контейнера `web`.

## Оценка поиска по фото

- `eval_search.py` — оценка полного `SearchService` (OCR + SIFT + ranking). Синтетика не равна точности на реальных фото.
- `smoke_search.py` — HTTP smoke контракта retrieval API.
- `eval.py`, `eval_augmentations.py` — старая синтетическая оценка только `SiftIndex` на аугментациях эталонов.
- `audit_mapping.py` — аудит привязки фото к винам: читает привязку из PostgreSQL, картинки из MinIO и сравнивает эмбеддинги. Пишет `reports/mapping_audit_<дата>.json` и `reports/image-overrides-proposed.csv` в формате `db/image-overrides.csv`. Предложения не применяются автоматически: проверьте строки и перенесите нужные в `db/image-overrides.csv`, после чего выполните `docker compose up -d`.
- `eval.py`, `eval_search.py` берут текущий SIFT-индекс и эталонные картинки из MinIO; аргументы `--index` и `--dataset` больше не нужны.
- `label_prep.py` — подготовка эталонов для экспериментального retriever (`docs/2b_RETRIEVER.md`).

Сырые JSON-результаты пишутся в `reports/` и не коммитятся; в git остаются только сводки.

## Сомелье

- `eval-sommelier.ts` — русский red-team набор против запущенного сервера (`npm run eval:sommelier`).
