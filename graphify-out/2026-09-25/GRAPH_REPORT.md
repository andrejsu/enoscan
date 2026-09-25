# Graph Report - enoscan  (2026-09-25)

## Corpus Check
- 173 files · ~317,411 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1440 nodes · 2723 edges · 98 communities (87 shown, 11 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 334 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `db16b937`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_mapping.py|mapping.py]]
- [[_COMMUNITY_label_prep.py|label_prep.py]]
- [[_COMMUNITY_index.ts|index.ts]]
- [[_COMMUNITY_План разработки сканера российских вин|План разработки сканера российских вин]]
- [[_COMMUNITY_chat.post.ts|chat.post.ts]]
- [[_COMMUNITY_4. Рекомендуемый профиль каждого знака|4. Рекомендуемый профиль каждого знака]]
- [[_COMMUNITY_Поиск вина по фотографии с текущим Tesseract|Поиск вина по фотографии с текущим Tesseract]]
- [[_COMMUNITY_catalog-admin.ts|catalog-admin.ts]]
- [[_COMMUNITY_dependencies|dependencies]]
- [[_COMMUNITY_main.py|main.py]]
- [[_COMMUNITY_catalog.py|catalog.py]]
- [[_COMMUNITY_retriever_main.py|retriever_main.py]]
- [[_COMMUNITY_index_store.py|index_store.py]]
- [[_COMMUNITY_ocr_retriever.py|ocr_retriever.py]]
- [[_COMMUNITY_images.py|images.py]]
- [[_COMMUNITY_Wine|Wine]]
- [[_COMMUNITY_ImageFeatures|ImageFeatures]]
- [[_COMMUNITY_ranking_main.py|ranking_main.py]]
- [[_COMMUNITY_OcrRetriever|OcrRetriever]]
- [[_COMMUNITY_run.py|run.py]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_EmbeddingStore|EmbeddingStore]]
- [[_COMMUNITY_test_run.py|test_run.py]]
- [[_COMMUNITY_label_normalize.py|label_normalize.py]]
- [[_COMMUNITY_config.py|config.py]]
- [[_COMMUNITY_index.vue|index.vue]]
- [[_COMMUNITY_audit_mapping.py|audit_mapping.py]]
- [[_COMMUNITY_scripts|scripts]]
- [[_COMMUNITY_Ретривер винных этикеток (standalone, отключён от основного сканера)|Ретривер винных этикеток (standalone, отключён от основного сканера)]]
- [[_COMMUNITY_eval_augmentations.py|eval_augmentations.py]]
- [[_COMMUNITY_ObjectStore|ObjectStore]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_storage.py|storage.py]]
- [[_COMMUNITY_scan-debug.ts|scan-debug.ts]]
- [[_COMMUNITY_ScanDebugPanel.vue|ScanDebugPanel.vue]]
- [[_COMMUNITY_apply_migrations|apply_migrations]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_new.vue|new.vue]]
- [[_COMMUNITY_Правила разработки Vinolog|Правила разработки Vinolog]]
- [[_COMMUNITY_README|README.md]]
- [[_COMMUNITY_Interview Answers|Interview Answers]]
- [[_COMMUNITY_Wine Scanner Retrieval Upgrade DINOv3 + OCR Hard Filter + Noise Robustness|Wine Scanner Retrieval Upgrade: DINOv3 + OCR Hard Filter + Noise Robustness]]
- [[_COMMUNITY_Импорт каталога и изображений в Postgres + MinIO|Импорт каталога и изображений в Postgres + MinIO]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_Changes Required|Changes Required]]
- [[_COMMUNITY_WineResultCard.vue|WineResultCard.vue]]
- [[_COMMUNITY_sommelier.vue|sommelier.vue]]
- [[_COMMUNITY_main|main]]
- [[_COMMUNITY_useSommelierChat.ts|useSommelierChat.ts]]
- [[_COMMUNITY_Importer|Importer]]
- [[_COMMUNITY_AdminWineCard.vue|AdminWineCard.vue]]
- [[_COMMUNITY_CatalogImageLightbox.vue|CatalogImageLightbox.vue]]
- [[_COMMUNITY_Phase 0 Synthetic Eval Harness|Phase 0: Synthetic Eval Harness]]
- [[_COMMUNITY_Phase 1 Catalog Mapping Audit|Phase 1: Catalog Mapping Audit]]
- [[_COMMUNITY_Phase 2 Augmented Index Rebuild|Phase 2: Augmented Index Rebuild]]
- [[_COMMUNITY_Phase 3 DINOv3 First-Pass Retrieval|Phase 3: DINOv3 First-Pass Retrieval]]
- [[_COMMUNITY_Phase 4 OCR as Hard Filter|Phase 4: OCR as Hard Filter]]
- [[_COMMUNITY_ScannerPanel.vue|ScannerPanel.vue]]
- [[_COMMUNITY_index.vue|index.vue]]
- [[_COMMUNITY_Checks|Checks]]
- [[_COMMUNITY_Phase 5 Fix evalpredict and Alternatives|Phase 5: Fix eval/predict and Alternatives]]
- [[_COMMUNITY_Nuxt Minimal Starter|Nuxt Minimal Starter]]
- [[_COMMUNITY_tsconfig.json|tsconfig.json]]
- [[_COMMUNITY_Scripts|Scripts]]
- [[_COMMUNITY_Phase 2 Importer|Phase 2: Importer]]
- [[_COMMUNITY_Phase 4 Retriever на pgvector|Phase 4: Retriever на pgvector]]
- [[_COMMUNITY_AppHeader.vue|AppHeader.vue]]
- [[_COMMUNITY_ZodiacMark.vue|ZodiacMark.vue]]
- [[_COMMUNITY_scan-file.ts|scan-file.ts]]
- [[_COMMUNITY_feature-flags.ts|feature-flags.ts]]
- [[_COMMUNITY_scans.post.ts|scans.post.ts]]
- [[_COMMUNITY_Retrieval service|Retrieval service]]
- [[_COMMUNITY_Testing Strategy|Testing Strategy]]
- [[_COMMUNITY_useAstroRecommendations.ts|useAstroRecommendations.ts]]
- [[_COMMUNITY_useWineScanner.ts|useWineScanner.ts]]
- [[_COMMUNITY_scan-debug-mock.ts|scan-debug-mock.ts]]
- [[_COMMUNITY_smoke_search.py|smoke_search.py]]
- [[_COMMUNITY_Status (updated 2026-09-16)|Status (updated 2026-09-16)]]
- [[_COMMUNITY_tsconfig.json|tsconfig.json]]
- [[_COMMUNITY_AGENTS|AGENTS.md]]
- [[_COMMUNITY_astro-sommelier.vue|astro-sommelier.vue]]
- [[_COMMUNITY_index.vue|index.vue]]
- [[_COMMUNITY_zodiac-wine.test.ts|zodiac-wine.test.ts]]
- [[_COMMUNITY_dev-entrypoint.sh|dev-entrypoint.sh]]
- [[_COMMUNITY_dev-shell.sh|dev-shell.sh]]

## God Nodes (most connected - your core abstractions)
1. `Wine` - 47 edges
2. `RetrievalFields` - 47 edges
3. `rank()` - 38 edges
4. `FieldCandidate` - 37 edges
5. `FieldVocabulary` - 23 edges
6. `run_import()` - 21 edges
7. `wine()` - 20 edges
8. `EmbeddingStore` - 18 edges
9. `resolve_mappings()` - 17 edges
10. `ObjectStore` - 17 edges

## Surprising Connections (you probably didn't know these)
- `useWineScanner()` --indirect_call--> `scan()`  [INFERRED]
  apps/web/app/composables/useWineScanner.ts → services/retrieval/tests/test_ranking_main.py
- `run_audit()` --calls--> `load_references()`  [INFERRED]
  scripts/audit_mapping.py → services/retrieval/app/catalog.py
- `run_eval()` --calls--> `load_references()`  [INFERRED]
  scripts/eval.py → services/retrieval/app/catalog.py
- `run_eval()` --calls--> `current_index_path()`  [INFERRED]
  scripts/eval.py → services/retrieval/app/index_store.py
- `scan()` --indirect_call--> `post_image()`  [INFERRED]
  services/retrieval/tests/test_ranking_main.py → scripts/eval_ranking.py

## Import Cycles
- None detected.

## Communities (98 total, 11 thin omitted)

### Community 0 - "mapping.py"
Cohesion: 0.05
Nodes (88): ArchiveReader, CatalogParseResult, CatalogWine, clean(), Issue, parse_rows(), Path, read_catalog() (+80 more)

### Community 1 - "label_prep.py"
Cohesion: 0.09
Nodes (46): clean_mask(), Config, contour_points(), debug_geometry(), debug_segmentation(), _edge_bins(), ensure_sam(), estimate_geometry() (+38 more)

### Community 2 - "index.ts"
Cohesion: 0.06
Nodes (31): AstroRecommendationResponse, CatalogAdminResponse, CatalogImageStatus, catalogImageStatuses, CatalogMappingKind, CatalogPagination, CatalogReviewStatus, CatalogSummary (+23 more)

### Community 3 - "План разработки сканера российских вин"
Cohesion: 0.04
Nodes (45): 10 Мобильный интерфейс и скорость, 11 План на 5 рабочих дней, 12 Задачи и контрольные точки, 13 Эксперименты и риски, 14 Защита и комплект сдачи, 15 Приёмка и источники, 1 Приоритеты по критериям, 2 Требования и вопросы организаторам (+37 more)

### Community 4 - "chat.post.ts"
Cohesion: 0.09
Nodes (27): SommelierAdversarialCase, sommelierAdversarialCases, answerSchema, classifySommelierInput(), classifySommelierOutput(), generateSommelierAnswer(), guardVerdictSchema, providerOptions (+19 more)

### Community 5 - "4. Рекомендуемый профиль каждого знака"
Cohesion: 0.05
Nodes (39): 10. Как проверить ценность фичи, 11. Приоритет реализации, 12. Источники и что из них взято, 1. Что именно связывают с вином, 2. Научная рамка и честная подача, 3. Базовая астрологическая сетка, 4. Рекомендуемый профиль каждого знака, 5. Почему источники называют разные вина (+31 more)

### Community 6 - "Поиск вина по фотографии с текущим Tesseract"
Cohesion: 0.05
Nodes (35): OCR, визуальный поиск и объединение кандидатов, Архитектура Vinolog, Границы системы, Данные и индексы, Два контракта поиска, Инварианты, Поток цифрового сомелье, Текущий поток (+27 more)

### Community 7 - "catalog-admin.ts"
Cohesion: 0.08
Nodes (27): AdminQuery, AdminRow, browseCatalog(), imageStatusConditions, loadSummary(), loadWines(), parseAdminQuery(), SummaryRow (+19 more)

### Community 8 - "dependencies"
Cohesion: 0.06
Nodes (34): dependencies, ai, @ai-sdk/anthropic, @ai-sdk/google, @ai-sdk/openai, @aws-sdk/client-s3, @fontsource/source-sans-3, @fontsource/source-serif-4 (+26 more)

### Community 9 - "main.py"
Cohesion: 0.17
Nodes (17): Candidate, SearchResult, ImageFeatures, Candidate, ndarray, SearchResult, SiftIndex, ProductResult (+9 more)

### Community 11 - "catalog.py"
Cohesion: 0.26
Nodes (11): main(), decode_image(), decode_reference(), extract_features(), ndarray, _root_sift(), IndexedReference, save_index() (+3 more)

### Community 12 - "retriever_main.py"
Cohesion: 0.20
Nodes (12): main(), Build the retriever's own index — separate object, separate process from app/bui, current_dataset_version(), load_references(), Reference, DINOv2 reference embeddings stored in PostgreSQL (pgvector).  Embeddings are key, Local wine-label retrieval service., decode_reference_unchanged() (+4 more)

### Community 13 - "index_store.py"
Cohesion: 0.20
Nodes (19): current_index_path(), fetch_index(), find_build(), IndexBuild, IndexedImage, object_key_for(), publish_index(), ObjectStore (+11 more)

### Community 14 - "ocr_retriever.py"
Cohesion: 0.06
Nodes (63): Pattern, load_wines(), extract_label(), fold_homoglyphs(), load_engine(), OcrResult, OcrWord, ndarray (+55 more)

### Community 16 - "images.py"
Cohesion: 0.06
Nodes (51): ClientError, Image, ArchiveMember, ArchiveStats, classify(), iter_originals(), Path, strapi_path_of() (+43 more)

### Community 17 - "Wine"
Cohesion: 0.12
Nodes (16): ScannerState, useWineScanner(), IndexedReference, scan(), test_both_services_down_is_an_infrastructure_error_not_not_found(), test_eval_route_answers_unsure_top1_under_top1_policy(), test_eval_route_leaves_unsure_answer_empty_under_the_default_policy(), test_eval_route_rejects_a_broken_file_and_reports_outages() (+8 more)

### Community 18 - "ImageFeatures"
Cohesion: 0.11
Nodes (19): LabelConfig, Dinov2Encoder, ndarray, Path, Frozen DINOv2 global descriptor for wine-label instance retrieval.  Global embed, Read catalog art with transparent pixels composited onto white., read_embedding_image(), EmbeddingStore (+11 more)

### Community 19 - "ranking_main.py"
Cohesion: 0.06
Nodes (100): _optional(), Wine, FieldCandidate, fields_from_json(), Shared evidence struct for the OCR block and the visual retriever.  Both sources, Inverse of dataclasses.asdict(RetrievalFields) — how the OCR service     (app/oc, RetrievalFields, extract_year() (+92 more)

### Community 20 - "OcrRetriever"
Cohesion: 0.16
Nodes (14): decode_upload(), ndarray, UploadFile, read_image_upload(), lifespan(), product_search(), FastAPI, UploadFile (+6 more)

### Community 21 - "run.py"
Cohesion: 0.18
Nodes (13): CatalogAdminWine, WineCard, CatalogSearchFilters, catalogSearchFiltersSchema, SommelierBlockReason, SommelierConversationMessage, SommelierMessageInput, sommelierMessageSchema (+5 more)

### Community 22 - "Changes Required"
Cohesion: 0.14
Nodes (14): 10. `services/retrieval/app/config.py`, 11. Удалить `services/retrieval/app/catalog_browser.py`, 12. `compose.yaml`, 13. Тесты, 1. `services/retrieval/requirements.txt`, 2. `services/retrieval/app/storage.py`, 3. `services/retrieval/app/catalog.py`, 4. `services/retrieval/app/index_store.py` (+6 more)

### Community 23 - "EmbeddingStore"
Cohesion: 0.33
Nodes (4): ObjectStore, Path, storage_from_environment(), StorageSettings

### Community 24 - "test_run.py"
Cohesion: 0.48
Nodes (3): candidate(), CatalogTest, wine()

### Community 25 - "label_normalize.py"
Cohesion: 0.17
Nodes (12): Pre-fetch the SAM segmentation model used by label_normalize's query path.  Segm, _fast_crop(), prepare_query(), prepare_reference_image(), PreparedQuery, ndarray, Bridge to scripts/label_prep.py: normalize both catalog art and query photos ont, Locate the horizontal label band on a transparent catalog bottle cutout. (+4 more)

### Community 26 - "config.py"
Cohesion: 0.60
Nodes (4): digest(), main(), Path, Download the pinned public DINOv2 ONNX checkpoint into the model volume.

### Community 27 - "index.vue"
Cohesion: 0.13
Nodes (9): appliedSearch, { data, status, error, refresh }, draftSearch, imageStatus, importedAt, page, requestQuery, selectedWine (+1 more)

### Community 28 - "audit_mapping.py"
Cohesion: 0.30
Nodes (14): InferenceSession, embed_objects(), flag_suspicious(), load_orphans(), load_session(), main(), normalize_rows(), overrides_rows() (+6 more)

### Community 29 - "scripts"
Cohesion: 0.13
Nodes (14): engines, node, name, private, scripts, build, check, dev (+6 more)

### Community 30 - "Ретривер винных этикеток (standalone, отключён от основного сканера)"
Cohesion: 0.13
Nodes (14): API, `GET /health`, `GET /v1/wines/{slug}/image`, `POST /v1/search` — как вызвать, Архитектура, Если понадобится снова подключить к сканеру, Зачем он вообще есть, Как поднять отдельно (не трогая основной стек) (+6 more)

### Community 31 - "eval_augmentations.py"
Cohesion: 0.34
Nodes (13): blur(), brightness(), combined(), crop_zoom(), glare(), hard_combined(), hard_perspective(), jpeg() (+5 more)

### Community 32 - "ObjectStore"
Cohesion: 0.40
Nodes (5): Automated Verification:, Manual Verification:, Overview, Phase 3: SIFT-сервис `retrieval` и `retrieval-index`, Success Criteria

### Community 33 - "Changes Required"
Cohesion: 0.11
Nodes (19): 10. `apps/web/server/utils/sommelier-catalog.ts`, 11. UI, 12. `compose.yaml` (`web`), 13. Тесты (vitest), 1. `apps/web/shared/contracts/index.ts`, 2. `apps/web/nuxt.config.ts`, 3. `apps/web/package.json`, 4. `apps/web/server/utils/catalog-db.ts` (+11 more)

### Community 34 - "storage.py"
Cohesion: 0.23
Nodes (13): load_database_url(), load_max_upload_bytes(), load_settings(), Settings, _eval_policy(), load_ranking_settings(), RankingSettings, Settings for the standalone ranking service (app/ranking_main.py).  Where to rea (+5 more)

### Community 35 - "scan-debug.ts"
Cohesion: 0.20
Nodes (14): clampShare(), cropBoxStyle(), firstFieldWithCandidates(), formatScore(), rankingMatchLine(), RankingSegment, rankingSegments(), scanDebugFieldLabels (+6 more)

### Community 36 - "ScanDebugPanel.vue"
Cohesion: 0.14
Nodes (12): labelFacts, matchLine, preprocessingMetrics, props, rankingLegend, rankingRows, selectedCandidates, selectedField (+4 more)

### Community 37 - "apply_migrations"
Cohesion: 0.67
Nodes (3): getStableProfile(), matchScanWineToZodiac(), matchWineToZodiac()

### Community 38 - "Changes Required"
Cohesion: 0.18
Nodes (11): 10. Тесты, 1. `services/retrieval/app/embedding.py`, 2. `services/retrieval/app/label_normalize.py`, 3. `services/retrieval/app/embedding_store.py`, 4. `services/retrieval/app/retriever_index.py`, 5. `services/retrieval/app/retriever.py`, 6. `services/retrieval/app/build_retriever_index.py`, 7. `services/retrieval/app/retriever_main.py` (+3 more)

### Community 39 - "new.vue"
Cohesion: 0.20
Nodes (8): dish, isSaved, preference, route, router, { save }, verdict, wine

### Community 40 - "Правила разработки Vinolog"
Cohesion: 0.20
Nodes (9): Nuxt 4 и Vue, TypeScript и данные, Имена и размер модулей, Интерфейс, Контракты поиска, Направление зависимостей, Правила разработки Vinolog, Проверки готовности (+1 more)

### Community 41 - "README.md"
Cohesion: 0.10
Nodes (18): `.env` на сервере, SSH-ключ для GitHub Actions, Датасет, Деплой на VPS, Настройки GitHub, Однократная настройка сервера, Эксплуатация, Docker (+10 more)

### Community 43 - "Interview Answers"
Cohesion: 0.20
Nodes (9): Interview Answers, Key Requirements Extracted, Open Questions, Original Description, Q1 (Goal): What matters more for the competition — accuracy (correct slug in top-1) or speed (latency_ms)?, Q2 (Hardware): Will the container run on CPU only or is GPU possible?, Q3 (Scope): What is in scope for the plan?, Q4 (Eval): How to measure improvement? (+1 more)

### Community 44 - "Wine Scanner Retrieval Upgrade: DINOv3 + OCR Hard Filter + Noise Robustness"
Cohesion: 0.20
Nodes (10): Current State Analysis, Desired End State, Implementation Approach, Migration Notes, Overview, Performance Considerations, References, Testing Strategy (+2 more)

### Community 45 - "Импорт каталога и изображений в Postgres + MinIO"
Cohesion: 0.20
Nodes (9): Current State Analysis, Desired End State, Implementation Approach, Migration Notes, Overview, Performance Considerations, References, What We're NOT Doing (+1 more)

### Community 46 - "Changes Required"
Cohesion: 0.20
Nodes (10): 1. `compose.yaml`, 2. `services/importer/`, 3. `db/migrations/001_catalog_schema.sql`, 4. `.env.example`, Automated Verification:, Changes Required, Manual Verification:, Overview (+2 more)

### Community 47 - "Changes Required"
Cohesion: 0.20
Nodes (10): 1. `importer/versioning.py`, 2. `importer/catalog_csv.py`, 3. `importer/archive.py`, 4. `importer/images.py`, 5. `importer/mapping.py`, 6. `importer/overrides.py`, 7. `importer/eval_sets.py`, 8. `importer/run.py` и `__main__.py` (+2 more)

### Community 48 - "Changes Required"
Cohesion: 0.20
Nodes (10): 1. `scripts/audit_mapping.py`, 2. `scripts/eval.py`, `scripts/eval_search.py`, 3. Удаление, 4. Документация, Automated Verification:, Changes Required, Manual Verification:, Overview (+2 more)

### Community 49 - "WineResultCard.vue"
Cohesion: 0.22
Nodes (8): config, displayedWine, emit, isAstroEnabled, pairingQuery, props, selectedWine, zodiacMatch

### Community 50 - "sommelier.vue"
Cohesion: 0.22
Nodes (6): { clear, errorMessage, isSubmitting, messages, retry, send }, config, conversationEnd, draft, isMock, suggestions

### Community 51 - "main"
Cohesion: 0.19
Nodes (8): main(), run_eval(), main(), Path, read_manifest(), summarize(), test_manifest_rejects_capture_group_leakage(), test_unlabelled_manifest_is_not_unknown()

### Community 53 - "useSommelierChat.ts"
Cohesion: 0.39
Nodes (6): isConversationMessage(), isWineCard(), newId(), restoreConversation(), SommelierChatState, useSommelierChat()

### Community 55 - "Importer"
Cohesion: 0.25
Nodes (7): `db/image-overrides.csv`, Importer, Входы, Коды выхода, Привязка фото, Тесты, Этапы

### Community 56 - "AdminWineCard.vue"
Cohesion: 0.33
Nodes (6): emit, handleImageRequest(), imageStatus, mappingKindLabels, props, reviewStatusLabels

### Community 57 - "CatalogImageLightbox.vue"
Cohesion: 0.38
Nodes (6): closeDialog(), dialog, emit, handleBackdropClick(), handleClosed(), props

### Community 58 - "Phase 0: Synthetic Eval Harness"
Cohesion: 0.29
Nodes (7): Automated Verification, Changes Required, Implementation Notes, Manual Verification, Phase 0: Synthetic Eval Harness, Read Before Starting, Success Criteria

### Community 59 - "Phase 1: Catalog Mapping Audit"
Cohesion: 0.29
Nodes (7): Automated Verification, Changes Required, Implementation Notes, Manual Verification, Phase 1: Catalog Mapping Audit, Read Before Starting, Success Criteria

### Community 60 - "Phase 2: Augmented Index Rebuild"
Cohesion: 0.29
Nodes (7): Automated Verification, Changes Required, Implementation Notes, Manual Verification, Phase 2: Augmented Index Rebuild, Read Before Starting, Success Criteria

### Community 61 - "Phase 3: DINOv3 First-Pass Retrieval"
Cohesion: 0.29
Nodes (7): Automated Verification, Changes Required, Implementation Notes, Manual Verification, Phase 3: DINOv3 First-Pass Retrieval, Read Before Starting, Success Criteria

### Community 62 - "Phase 4: OCR as Hard Filter"
Cohesion: 0.29
Nodes (7): Automated Verification, Changes Required, Implementation Notes, Manual Verification, Phase 4: OCR as Hard Filter, Read Before Starting, Success Criteria

### Community 63 - "ScannerPanel.vue"
Cohesion: 0.16
Nodes (10): cameraInput, dragDepth, emit, galleryInput, handleDrop(), handleFileChange(), handleReset(), isDragging (+2 more)

### Community 64 - "index.vue"
Cohesion: 0.33
Nodes (5): error, panelStatus, previewUrl, response, scanner

### Community 65 - "Checks"
Cohesion: 0.33
Nodes (5): Checks, Coverage Matrix, Criticals, VERIFICATION.md — Plan Quality Assessment, Warnings

### Community 66 - "Phase 5: Fix eval/predict and Alternatives"
Cohesion: 0.33
Nodes (6): Automated Verification, Changes Required, Manual Verification, Phase 5: Fix eval/predict and Alternatives, Read Before Starting, Success Criteria

### Community 67 - "Nuxt Minimal Starter"
Cohesion: 0.40
Nodes (4): Development Server, Nuxt Minimal Starter, Production, Setup

### Community 68 - "tsconfig.json"
Cohesion: 0.40
Nodes (4): compilerOptions, noEmit, files, references

### Community 69 - "Scripts"
Cohesion: 0.40
Nodes (4): Scripts, Датасет и окружение, Оценка поиска по фото, Сомелье

### Community 70 - "Phase 2: Importer"
Cohesion: 0.40
Nodes (5): Automated Verification:, Manual Verification:, Overview, Phase 2: Importer, Success Criteria

### Community 71 - "Phase 4: Retriever на pgvector"
Cohesion: 0.40
Nodes (5): Automated Verification:, Manual Verification:, Overview, Phase 4: Retriever на pgvector, Success Criteria

### Community 73 - "AppHeader.vue"
Cohesion: 0.40
Nodes (4): config, isAstroEnabled, isSommelierEnabled, navItems

### Community 74 - "ZodiacMark.vue"
Cohesion: 0.50
Nodes (3): props, zodiacIcon, zodiacIcons

### Community 75 - "scan-file.ts"
Cohesion: 0.60
Nodes (3): acceptedScanTypes, getFirstScanFile(), validateScanFile()

### Community 78 - "scans.post.ts"
Cohesion: 0.50
Nodes (3): acceptedTypes, demoAlternative, demoWine

### Community 80 - "Retrieval service"
Cohesion: 0.50
Nodes (3): Retrieval service, Запуск, Хранилища

### Community 81 - "Testing Strategy"
Cohesion: 0.50
Nodes (4): Integration Tests, Manual Testing Steps, Testing Strategy, Unit Tests

### Community 84 - "useWineScanner.ts"
Cohesion: 0.16
Nodes (22): attach_labels(), _f1(), main(), organizer_slug(), post_image(), Path, _ratio(), (HTTP status or None on timeout/network error, JSON body or None, ms). (+14 more)

### Community 87 - "Status (updated 2026-09-16)"
Cohesion: 0.67
Nodes (3): Findings that change later phases, Measured baseline (blocks the original Phase 2/3 gates), Status (updated 2026-09-16)

## Knowledge Gaps
- **467 isolated node(s):** `mappingKindLabels`, `reviewStatusLabels`, `props`, `imageStatus`, `config` (+462 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Config` connect `label_prep.py` to `images.py`, `label_normalize.py`, `EmbeddingStore`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `ImageDecodeError` connect `images.py` to `mapping.py`, `catalog.py`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `Wine` connect `ranking_main.py` to `main.py`, `catalog.py`, `retriever_main.py`, `ocr_retriever.py`, `Wine`, `ImageFeatures`, `main`, `test_run.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `Wine` (e.g. with `Candidate` and `IndexedReference`) actually correct?**
  _`Wine` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `RetrievalFields` (e.g. with `FieldContribution` and `LabelCheck`) actually correct?**
  _`RetrievalFields` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `rank()` (e.g. with `test_patterned_label_reads_the_winery_but_winery_alone_never_matches()` and `test_readable_label_yields_the_wine_name()`) actually correct?**
  _`rank()` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `FieldCandidate` (e.g. with `FieldContribution` and `LabelCheck`) actually correct?**
  _`FieldCandidate` has 24 INFERRED edges - model-reasoned connections that need verification._