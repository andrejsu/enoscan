# Importer

Одноразовый сервис, который переносит исходный набор из `data/dataset/` в PostgreSQL и MinIO. В Compose он запускается перед индексаторами и web; повторный запуск с теми же данными завершается за секунды.

## Входы

- `/input/strapi_output0709.csv` и три тома `prod-svoe-vino-strapi.part{1,2,3}.rar` — обязательны.
- `/input/eval.zip`, `/input/Реальные фото.zip` — необязательны, загружаются в бакет `vinolog-eval` (префиксы `eval/` и `real-photos/`).
- `/db/migrations/*.sql` — схема; применяется по порядку имён, факт применения и sha256 файла пишутся в `schema_migrations`. Если уже применённый файл изменился, importer останавливается: схему меняют только новой миграцией.
- `/db/image-overrides.csv` — ручные исправления привязки фото.

## Этапы

1. Миграции и бакеты `vinolog-images`, `vinolog-indexes`, `vinolog-eval`.
2. `dataset_version` = sha256 от хэшей CSV, томов RAR, overrides, `MAPPING_ALGO_VERSION` и `PREVIEW_VERSION` (`importer/versioning.py`). Если версия совпадает с последним успешным `import_runs`, работа на этом заканчивается.
3. Картинки. Оригиналы `jpg/jpeg/png/webp` из `strapi/uploads/` читаются из RAR по одному, копии Strapi `thumbnail_/small_/medium_/large_` пропускаются. Объект `originals/<sha[:2]>/<sha>.<ext>` и превью WebP (не больше 400×600) `previews/<PREVIEW_VERSION>/...` загружаются, только если их ещё нет. Файлы, которые не декодируются, попадают в `import_issues` как `image_decode_failed`. Если архив и версия превью не менялись с прошлого успешного импорта, этап пропускается.
4. Проверочные наборы в `vinolog-eval`.
5. Одна транзакция: `catalog_rows_raw`, upsert `wines` (первая строка slug побеждает, дубли — issue `duplicate_slug`, пропавшие из CSV вина получают `is_active = false`), привязка фото, overrides, `import_issues`, статистика в `import_runs.stats`.

## Привязка фото

Порядок: имя фото из CSV, затем `slug`, затем сходство токенов имени (`importer/mapping.py`). Точные совпадения могут делить один файл между винами, fuzzy берёт только ещё не занятые файлы. Автоматическая привязка помечается `suspicious`, если картинку делят несколько вин (issue `shared_image`) или fuzzy-оценка ниже 0.85.

## `db/image-overrides.csv`

```csv
slug,action,strapi_filename,note
```

- `set` — основное фото = файл архива с этим именем (`mapping_kind = manual`, `review_status = confirmed`). Если файл был привязан к другому вину, та привязка снимается, в журнал пишется issue `override_displaced`.
- `reject` — снять автоматическую привязку.
- `confirm` — подтвердить автоматическую привязку.

Неизвестный или неактивный slug, неоднозначное или отсутствующее имя файла, два действия на один slug — importer останавливается с номером строки, run получает статус `failed`, данные прошлого импорта остаются нетронутыми.

## Коды выхода

- `0` — импорт выполнен или версия уже импортирована.
- `1` — ошибка (нет входных файлов, ошибка overrides, недоступны PostgreSQL или MinIO). Для начатого run причина записывается в `import_runs.error`.

## Тесты

```bash
docker compose run --rm importer python -m pytest tests -q -p no:cacheprovider
```

Тесты с БД создают и удаляют временную базу `vinolog_test_*` на сервисе `db`; MinIO в них заменён хранилищем в памяти.
