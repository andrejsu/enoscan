# Scripts

## Датасет и окружение

- `init-dataset.sh` — распаковывает архивы из `data/dataset/` в volume `dataset` (сервис `dataset-init`).
- `build-media-manifest.py` — строит манифест медиафайлов каталога; вызывается из `init-dataset.sh`.
- `dev-entrypoint.sh`, `dev-shell.sh` — entrypoint и shell dev-контейнера `web`.

## Оценка поиска по фото

- `eval_search.py` — оценка полного `SearchService` (OCR + SIFT + ranking). Синтетика не равна точности на реальных фото.
- `smoke_search.py` — HTTP smoke контракта retrieval API.
- `eval.py`, `eval_augmentations.py` — старая синтетическая оценка только `SiftIndex` на аугментациях эталонов.
- `audit_mapping.py` — аудит привязки эталонных изображений к карточкам каталога.
- `label_prep.py` — подготовка эталонов для экспериментального retriever (`docs/2b_RETRIEVER.md`).

Сырые JSON-результаты пишутся в `reports/` и не коммитятся; в git остаются только сводки.

## Сомелье

- `eval-sommelier.ts` — русский red-team набор против запущенного сервера (`npm run eval:sommelier`).
