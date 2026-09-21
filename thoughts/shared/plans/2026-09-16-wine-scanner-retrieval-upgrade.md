# Wine Scanner Retrieval Upgrade: DINOv3 + OCR Hard Filter + Noise Robustness

> **Planning update (2026-09-21):** Follow [the Tesseract photo-retrieval plan](2026-09-21-photo-retrieval-tesseract.md) for subsequent work. It supersedes the hard year-filter recommendation and mandatory DINOv3 migration below. Historical completion records are retained; they do not establish current real-photo accuracy.

> **Date:** 2026-09-16
> **Repo:** Vinolog / `services/retrieval`
> **Competition target:** Recall@1 ≥ 0.95 on organizer eval

---

## Status (updated 2026-09-16)

| Phase | State | Notes |
|---|---|---|
| 0 — Synthetic eval harness | **done** | `scripts/eval.py` + `scripts/eval_augmentations.py`; baseline recorded; `--profile hard` added after the easy profile proved non-discriminative |
| 1 — Catalog mapping audit | **done** | `scripts/audit_mapping.py` + `reports/mapping_audit_2026-09-16.json`; one open item for the data team |
| 2 — Augmented index rebuild | **not started** | gate rewritten; see the note below before starting — real orphan photos may beat synthetic views |
| 3 — DINOv3 first-pass retrieval | **not started** | `onnxruntime` and the ONNX model are already in place from Phase 1 |
| 4 — OCR as hard filter | **done** | `extract_year` + `filter_by_year`; shortlist widened from 5 to 50 so OCR sees the whole list |
| 5 — Fix eval/predict and alternatives | **done** | 422 removed, `alternatives` filled, organizer script runs clean |

### Measured baseline (blocks the original Phase 2/3 gates)

`sift-v2.npz`, 200 refs, seed 42, both profiles:

| Profile | Recall@1 | Recall@5 | Recall@10 |
|---|---|---|---|
| `easy` (5 mild augmentations) | 0.958 | 0.996 | 0.996 |
| `hard` (7 shop-photo augmentations) | **0.832** | 0.875 | 0.876 |

Hard per-augmentation Recall@1: hard_perspective 0.970, crop_zoom 0.965, low_light 0.965,
glare 0.970, shelf 0.950, motion_blur 0.840, **hard_combined 0.165**. Each single degradation is
survivable; only the stacked one breaks the pipeline.

The plan assumed ~0.60–0.65, so the original gates (`baseline + 0.05` and `baseline + 0.15`)
resolve to 1.008 and 1.108 and cannot be met. Both were rewritten as residual-error reduction
on `--profile hard`, which gives concrete targets of 0.874 (Phase 2) and 0.916 (Phase 3).

Defect #1 in *Current State Analysis* ("FLANN recall is low") is **refuted on the easy profile and
confirmed on the hard one**. On hard, `Recall@10` (0.876) sits only 4.4 points above `Recall@1`
(0.832), so for roughly 12% of queries the correct wine is absent from the entire top-10 and no
amount of reranking can recover it. That is precisely the candidate-selection failure Phase 3
replaces, so DINOv3 now has a measured justification rather than an assumed one.

Both profiles still feed the index degraded copies of images it already holds, so even the hard
number measures near-duplicate retrieval and overstates accuracy on genuinely new photographs.
There is no labelled real-photo set to check against: the organizer `eval/` ships 3 images and
`queries.tsv` carries no expected-slug column. Treat 0.832 as an upper bound, not a forecast.

### Findings that change later phases

- **12 wines share byte-identical photos** with another wine (verified by sha256, e.g.
  `balaklava-pino-nuar` ↔ `bryut-beloe-zolotaya-balka`). No visual method can separate these —
  it is a hard ceiling, and only OCR can break the tie.
- **4104 original media files are unused** against 2098 indexed references, with catalog coverage
  at 2098/2103 wines. Phase 2 plans *synthetic* extra views while real alternate shots already sit
  in the dataset. Worth deciding whether Phase 2 should adopt orphan photos as additional views
  instead of generating blur and warp. This contradicts the *What We're NOT Doing* exclusion on
  multi-view references, which was written before the media count was known.
- **`scripts/eval.py` cannot measure Phase 4.** It calls `SiftIndex.search` directly and never
  constructs a `SearchService`, so OCR and the year filter are invisible to it. A service-level
  eval mode is needed before the Phase 4 no-regression gate means anything.

---

## Overview

Replace the FLANN descriptor-voting candidate selection with DINOv3 cosine similarity, harden OCR into a decisive year/name filter rather than a soft bonus, add augmented views at index build time to make SIFT robust to real-world photo noise, and audit the catalog→image mapping for fuzzy-linked errors. Measure every change against a synthetic Recall@1 benchmark built from reference images before touching production code.

---

## Current State Analysis

**What exists:**
- `services/retrieval/app/index.py` — SIFT+FLANN+RANSAC pipeline: votes over all descriptors via `FlannBasedMatcher(trees=4, checks=64)`, shortlists top-24, reranks with `BFMatcher+RANSAC` per candidate
- `services/retrieval/app/service.py` — calls `index.search(image, limit=5)` then Tesseract OCR, applies `+0.2 * text_score` as a soft bonus on top-5 only
- `services/retrieval/app/catalog.py` — fuzzy filename matcher for catalog→image binding; `mapping_score` is stored but never used at search time
- `services/retrieval/app/build_index.py` — one-shot build; exits early if `.npz` already exists; no augmentation

**Key defects identified:**
1. FLANN recall at `checks=64` over ~1M descriptors is low; if the correct wine is not in top-24, rerank and OCR cannot recover it
2. OCR text score runs only on top-5 candidates (after `limit=5` slicing in `search()`), not on the full shortlist
3. `text_score` is a soft +0.2 bonus — a correct year in the OCR output does not override a visually close but wrong wine
4. `/v1/eval/predict` raises HTTP 422 on empty shortlist instead of returning best guess
5. `mapping_kind=fuzzy_filename` entries share equal weight with exact matches; no audit of their accuracy
6. `alternatives` field always returned as `[]`

**Constraints:**
- CPU-only Docker container (`python:3.12-slim`); no PyTorch
- `onnxruntime` is the only allowed inference runtime; DINOv3 ONNX exports available at `onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX`
- DINOv3 license: commercial use permitted; "Built with DINOv3" attribution required in product or docs
- No pgvector: brute-force cosine over ~6000 vectors is faster and exact at this scale
- Index stored in a Docker volume (`vinolog_retrieval-index`); build re-runs by removing the volume and restarting `retrieval-index` service
- Test command: `python -m pytest services/retrieval/tests/` (from repo root)
- Lint: not defined in manifests — use `ruff check services/retrieval/`

---

## Desired End State

- ~~Synthetic `Recall@1 ≥ 0.80` on augmented reference eval set (up from estimated ~0.60–0.65 with current SIFT-only)~~
  **Superseded 2026-09-16 by measurement.** The mild-augmentation baseline is already `Recall@1 = 0.958`,
  so the 0.80 target was met before any work started. That profile feeds the index degraded copies of its own
  images, which overstates real accuracy; the `--profile hard` set (crop, glare, motion blur, low light, shelf
  background, strong warp) is the measuring stick from here on. No labelled real-photo set exists:
  the organizer `eval/` ships 3 images and `queries.tsv` carries no expected slug.
- Year tokens extracted by OCR filter candidates: if OCR year is confident, wines without that year in slug/name are excluded before scoring
- SIFT+RANSAC rerank runs on a shortlist built by DINOv3 cosine (top-50), not FLANN voting
- Index build applies N augmented views per reference image (blur, JPEG artefacts, perspective warp)
- Catalog mapping audit report: every `fuzzy_filename` entry is reviewed and corrected or flagged
- `/v1/eval/predict` always returns a slug (never 422)

---

## What We're NOT Doing

- Fine-tuning DINOv3 on wine domain data (requires labeled pairs, GPU, training infra — out of scope)
- Dense patch matching with DINOv3 features (too slow on CPU; SIFT serves this role)
- pgvector or ANN index (brute-force cosine is exact and faster at 6000 vectors)
- GPU deployment (CPU constraint; GPU is noted as future option)
- ETL changes to the Nuxt web layer or `apps/web/` (retrieval service is self-contained)
- Replacing Tesseract with a neural OCR model
- Multi-view reference images from different camera angles (only augmented views of the single existing photo)

---

## Implementation Approach

The phases follow a **measure → fix foundations → improve recall → fix scoring → fix contracts** order. No phase changes production behavior before the eval harness exists, so every diff is verifiable.

DINOv3 replaces only the candidate-selection stage (replacing `votes` dict in `SiftIndex.search()`). The `_rerank()` method is untouched. The `DINOIndex` class stores one 384-dim float32 CLS vector per reference image (~9 MB for 6000 wines vs ~360 MB for SIFT descriptors) and retrieves top-K by matrix cosine similarity in a single `numpy` call.

OCR hard filter: extract year via `re.search(r'\b(19|20)\d{2}\b', ocr_text)` with confidence gate. If found, filter `candidates` to those whose `wine.name + wine.slug` contains the year. This runs after DINOv3 retrieval and before SIFT rerank — it shrinks the shortlist, not expands it.

---

## Phase 0: Synthetic Eval Harness

**Priority:** P0
**Risk:** low (new script, no production code touched)

### Read Before Starting

- `services/retrieval/app/image_features.py` — `extract_features`, `read_image`, `decode_image` signatures
- `services/retrieval/app/index.py` — `SiftIndex.load`, `SiftIndex.search`, `SearchResult`, `Candidate`
- `data/dataset/eval.zip` — organizer eval format and `participant_test.sh` script
- `services/retrieval/app/config.py` — `load_settings` for `dataset_root` and `index_path`
- `services/retrieval/app/catalog.py` — `load_catalog`, `Wine`, `Media`

### Changes Required

- `scripts/eval.py` — new script: loads `SiftIndex`, iterates reference images, applies augmentations, measures Recall@1 and Recall@5
- `scripts/eval_augmentations.py` — augmentation functions extracted as a module (reused in Phase 2)

### Implementation Notes

The script:
1. Connects to Postgres (or reads from npz references directly) to get the ground-truth `(image_path, slug)` pairs
2. For each reference, generates M augmented query images (default M=5)
3. Runs `SiftIndex.search(augmented_image, limit=50)` for each query
4. Records whether the correct slug appears in top-1, top-5, top-10
5. Prints a report: `Recall@1`, `Recall@5`, `Recall@10`, slowest queries

Augmentations to apply (cv2 only, no new deps):
```
blur:        cv2.GaussianBlur(img, (15, 15), 0)
jpeg:        encode to JPEG at quality=40, decode back
perspective: cv2.warpPerspective with a mild 4-point random warp (~8% shift)
brightness:  cv2.convertScaleAbs with alpha=1.4, beta=30
combined:    blur + perspective applied together
```

### Success Criteria

#### Automated Verification

- [x] `python scripts/eval.py --index /path/to/sift-v2.npz --dataset /path/to/dataset --samples 200` exits 0 and prints a report with `Recall@1`, `Recall@5`, and per-augmentation breakdown
- [x] Script completes in under 10 minutes for 200 samples on current hardware
- [x] `python -m pytest services/retrieval/tests/` still passes

#### Manual Verification

- [x] Recall@1 baseline is recorded in a comment at the top of `scripts/eval.py` before any further changes
- [ ] At least one failure case (wrong top-1 slug) is inspected visually to confirm it is a genuine retrieval miss, not a script bug

---

## Phase 1: Catalog Mapping Audit

**Priority:** P1
**Risk:** low (offline script; modifies no production code or database directly)

### Read Before Starting

- `services/retrieval/app/catalog.py` — `resolve_references`, `Reference`, `_fuzzy_score`, `load_catalog`
- `services/retrieval/app/index.py` — `IndexedReference`, `SiftIndex.load` (to iterate existing references)
- `db/import-dataset.sh` — how `wine_catalog` and `wine_media` are populated

### Changes Required

- `scripts/audit_mapping.py` — new offline script: loads DINOv3 ViT-S/16 ONNX, embeds all reference images, computes pairwise cosine within each winery, flags pairs where the mapped image is closer to another wine than to its own slug

### Implementation Notes

The script uses the same ONNX model that Phase 3 will load at service startup:
1. Download `onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX` model file (cached to `~/.cache/huggingface/hub/` or a local path)
2. For each `IndexedReference` in the existing `.npz`, embed the reference image
3. Within each winery group, compute cosine matrix
4. Flag references where `mapping_kind == "fuzzy_filename"` and their cosine score to any other wine in the same winery exceeds 0.85 (likely wrong assignment)
5. For orphaned media (high-res images not used by any reference), find the nearest wine by cosine and propose the assignment

Output: `reports/mapping_audit_YYYY-MM-DD.json` with `suspicious`, `orphaned`, and `proposed_fixes` lists.

### Success Criteria

#### Automated Verification

- [x] `python scripts/audit_mapping.py --npz /path/to/sift-v2.npz --dataset /path/to/dataset` exits 0 and writes `reports/mapping_audit_*.json`
- [x] Report JSON is valid and contains keys `suspicious`, `orphaned`, `proposed_fixes`
- [x] `python -m pytest services/retrieval/tests/` still passes

#### Manual Verification

- [x] At least 5 `suspicious` entries are inspected by viewing both the wine's catalog entry and the mapped image side-by-side
- [ ] Any confirmed wrong mappings are corrected in the Strapi dataset or flagged for the data team

---

## Phase 2: Augmented Index Rebuild

**Priority:** P1
**Risk:** medium (changes `build_index.py`; requires volume rebuild to take effect)

### Read Before Starting

- `services/retrieval/app/build_index.py` — `main()`, `extract_features` call site, early-exit guard
- `services/retrieval/app/image_features.py` — `extract_features(image, max_side, feature_count)` signature
- `scripts/eval_augmentations.py` — from Phase 0, augmentation functions to reuse
- `compose.yaml` — `INDEX_PATH: /indexes/sift-v2.npz` and `retrieval-index` service definition

### Changes Required

- `services/retrieval/app/build_index.py` — add augmentation loop: for each resolved reference, run `extract_features` on the original image and on N augmented views; concatenate all `ImageFeatures` under the same `owner` index
- `scripts/eval_augmentations.py` — imported (no changes needed if Phase 0 extracted it properly)

### Implementation Notes

The `owner` array in the index already maps each descriptor back to a reference index. Augmented descriptors for the same image get the same `owner` value. No change to the index file format.

Feature count per view should be reduced to avoid bloating the index: `feature_count = 400` per view for N=3 augmented views → same total as current 700 (3×400 > 700, so cap at 500 or tune by measuring index size).

New env var `INDEX_AUGMENT_VIEWS` (default `3`) controls how many augmented views to add per reference.

```python
# ponytail: fixed augmentation set; make configurable if quality gains plateau
AUGMENTED_VIEWS = [blur_fn, jpeg_fn, perspective_fn]
```

Rebuilding the index: `docker compose run --rm retrieval-index` after removing or renaming the existing `.npz`.

### Success Criteria

#### Automated Verification

- [ ] `python -m app.build_index` completes without error and writes an `.npz` to `INDEX_PATH`
- [ ] The new `.npz` is no more than 3× the size of the original (size check guards against accidental explosion)
- [ ] `python scripts/eval.py --samples 200 --profile hard` on the rebuilt index reaches **Recall@1 ≥ 0.874**
      (≥25% cut of the 0.168 residual error over the 0.832 hard baseline; the original absolute +0.05 was
      unreachable because the easy-profile baseline is already 0.958)
- [ ] `python -m pytest services/retrieval/tests/` still passes

#### Manual Verification

- [ ] `INDEX_AUGMENT_VIEWS=0` produces an index functionally identical to the old build (sanity check)
- [ ] Startup time of the `retrieval` service is acceptable after loading the larger index

---

## Phase 3: DINOv3 First-Pass Retrieval

**Priority:** P0
**Risk:** medium (changes the core `SiftIndex.search()` path; requires new dependency `onnxruntime` in requirements.txt and new model file at startup)

### Read Before Starting

- `services/retrieval/app/index.py` — `SiftIndex.__init__`, `SiftIndex.search`, `SiftIndex.load`, `_rerank`, `Candidate`, `SearchResult`
- `services/retrieval/app/build_index.py` — to understand what gets stored in the `.npz` (must add DINOv3 embeddings)
- `services/retrieval/app/main.py` — `lifespan()` where `SiftIndex.load` is called; model download must happen here or at startup
- `services/retrieval/requirements.txt` — add `onnxruntime`
- `services/retrieval/Dockerfile` — check if any system libs needed for onnxruntime (none expected for CPU)

### Changes Required

- `services/retrieval/requirements.txt` — add `onnxruntime==1.20.*` (latest stable as of 2026-09)
- `services/retrieval/app/dino_index.py` — new module: `DinoIndex` class with `embed(image) -> np.ndarray` and `search(query_embedding, k) -> list[int]`
- `services/retrieval/app/build_index.py` — during build, embed each reference image with DINOv3 and store embeddings in the `.npz` as `dino_embeddings` array
- `services/retrieval/app/index.py` — `SiftIndex.load` reads `dino_embeddings` from `.npz`; `SiftIndex.search` replaces the FLANN vote loop with `DinoIndex.search(query_emb, k=50)` then calls `_rerank` on those 50 owners
- `services/retrieval/app/main.py` — download/cache ONNX model at lifespan startup; fail fast with clear error if missing

### Implementation Notes

`DinoIndex` is intentionally minimal:

```python
class DinoIndex:
    def __init__(self, embeddings: np.ndarray) -> None:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        self.embeddings = embeddings / np.maximum(norms, 1e-8)

    def embed(self, image: np.ndarray, session: ort.InferenceSession) -> np.ndarray:
        # resize to 224x224, normalize with ImageNet mean/std, run session
        ...

    def search(self, query: np.ndarray, k: int) -> list[int]:
        scores = self.embeddings @ query
        return np.argpartition(scores, -k)[-k:].tolist()
        # ponytail: argpartition O(n), k=50 on 6000 rows is ~0.1ms; no ANN needed
```

ONNX model download: use `huggingface_hub.hf_hub_download` (already dependency-free pattern) or bundle the model file in the Docker image via a `RUN` step. Prefer bundling to avoid network dependency at runtime.

DINOv3 input preprocessing (standard ViT): resize to 224×224, `float32`, normalize with `mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]`, add batch dim. Output: `last_hidden_state[:, 0, :]` (CLS token) = 384-dim.

Build index change: add a second loop after SIFT extraction that embeds each reference image and writes `dino_embeddings` as shape `(N_references, 384)` to the same `.npz`. Build time increases by ~N_refs × 35 ms (single-threaded ViT-S inference); for 6000 refs ≈ 3.5 min extra.

The `dino_embeddings` key is read in `SiftIndex.load`; if the key is absent (old `.npz`), fall back to FLANN mode with a logged warning so old indexes remain functional.

### Success Criteria

#### Automated Verification

- [x] `onnxruntime` importable in the container: `docker compose run --rm retrieval python -c "import onnxruntime; print(onnxruntime.__version__)"` — verified during Phase 1 (`onnxruntime 1.20.1`)
- [ ] `python scripts/eval.py --samples 200 --profile hard` with DINOv3 shortlist reaches **Recall@1 ≥ 0.916**
      (≥50% cut of the 0.168 residual error over the 0.832 hard baseline; the original absolute +0.15 was unreachable)
- [ ] `Recall@10` on `--profile hard` rises well above `Recall@1`, proving the shortlist now contains the answer
      even when rerank picks wrong (baseline gap is only 0.044, which is the defect DINOv3 is meant to fix)
- [x] ~~`Recall@5` ≥ 0.90~~ already 0.996 on the easy profile at baseline; re-gate on the hard profile instead
- [ ] `python -m pytest services/retrieval/tests/` still passes
- [ ] Old `.npz` (without `dino_embeddings`) loads without crash and logs a fallback warning

#### Manual Verification

- [ ] `GET /health` returns `{"status": "ok"}` after container restart with new index
- [ ] `/v1/search` latency measured for 5 real wine photos; p95 ≤ 3 s on dev machine
- [ ] One wine with a blurry/angled photo is tested manually — result improves or stays equal vs FLANN baseline

---

## Phase 4: OCR as Hard Filter

**Priority:** P1
**Risk:** low (changes only `service.py`; no index rebuild needed; can be toggled off by reverting one function)

### Read Before Starting

- `services/retrieval/app/service.py` — `SearchService.search()`, `_product_body()`, current `text_score` usage
- `services/retrieval/app/ocr.py` — `extract_label_text`, `text_score`, `_tokens`, `STOP_WORDS`
- `services/retrieval/app/catalog.py` — `Wine.name`, `Wine.slug` structure (year in name, e.g. "Ребус 2019")
- `services/retrieval/tests/test_catalog.py` — `test_ocr_text_breaks_duplicate_image_tie` test to extend

### Changes Required

- `services/retrieval/app/ocr.py` — add `extract_year(text: str) -> int | None` function
- `services/retrieval/app/service.py` — replace the soft `+0.2 * text_score` bonus with a two-stage approach:
  1. If OCR year is found and confident: filter candidates to those with matching year; if no candidates survive, skip filter (fail-open)
  2. Apply `text_score` reranking on the surviving set (weight unchanged at 0.2, now on a pre-filtered set)
- `services/retrieval/tests/test_catalog.py` — add test: OCR year "2019" with candidates [slug-2019, slug-2020] → slug-2019 wins

### Implementation Notes

```python
def extract_year(text: str) -> int | None:
    matches = re.findall(r'\b(19[5-9]\d|20[012]\d)\b', text)
    if len(matches) == 1:
        return int(matches[0])
    return None  # ambiguous or absent — skip filter
```

Year filter is applied before SIFT rerank in `SearchService.search()`:
```python
ocr_year = extract_year(label_text)
if ocr_year and any(str(ocr_year) in c.wine.name + c.wine.slug for c in candidates):
    candidates = [c for c in candidates if str(ocr_year) in c.wine.name + c.wine.slug]
```

Fail-open: if the filter would empty the list, skip it. This avoids degradation when OCR misreads a digit.

OCR still runs on the full shortlist (top-50 from DINOv3, before SIFT rerank). After year filter, `_rerank()` runs on the survivors.

### Success Criteria

#### Automated Verification

- [x] `extract_year("Урожай 2019 года")` returns `2019`
- [x] `extract_year("2019 или 2020 неизвестно")` returns `None` (ambiguous)
- [x] `extract_year("красное вино")` returns `None`
- [x] Year filter test: candidates [wine-2019, wine-2020], OCR year=2019 → top-1 is wine-2019
- [x] Year filter fail-open test: candidates [wine-2020, wine-2021], OCR year=2019 → both candidates remain (filter skipped)
- [x] `python -m pytest services/retrieval/tests/` still passes
- [ ] `python scripts/eval.py --samples 200` Recall@1 does not regress vs Phase 3 (OCR filter must not hurt overall recall)
      **Not measurable with the current harness:** `scripts/eval.py` calls `SiftIndex.search` directly and never
      goes through `SearchService`, so neither OCR nor the year filter is exercised. Needs a service-level eval mode.

#### Manual Verification

- [ ] Photo of "Ребус 2019" tested: if OCR reads "2019", the 2020 vintage is excluded from result
- [x] Photo with no visible year tested: filter is skipped, no change in behavior

---

## Phase 5: Fix eval/predict and Alternatives

**Priority:** P1
**Risk:** low (isolated API surface changes; no index or model changes)

### Read Before Starting

- `services/retrieval/app/main.py` — `evaluation_search()` endpoint at `/v1/eval/predict`, lines 113–123
- `services/retrieval/app/service.py` — `_product_body()`, `alternatives` field currently `[]`
- `packages/contracts/` — `ScanResponse` type to confirm `alternatives` field type

### Changes Required

- `services/retrieval/app/main.py` — `evaluation_search`: remove 422 on empty candidates; return `{"slug": candidates[0]["slug"]}` if any candidates exist, else return `{"slug": ""}` (empty string signals no result without erroring)
- `services/retrieval/app/service.py` — `_product_body`: fill `alternatives` with top-3 candidates excluding the top-1 match, formatted as `WineCard` dicts

### Success Criteria

#### Automated Verification

- [x] `POST /v1/eval/predict` with a completely black image (no features) returns HTTP 200 with `{"slug": ""}` instead of 422
- [x] `POST /v1/search` response `alternatives` is a non-empty list when `status == "uncertain"` or `status == "not_found"`
      (holds whenever the shortlist has ≥2 entries; a featureless image yields 0 candidates and therefore 0
      alternatives — there is nothing to offer. Verified `uncertain` + 3 alternatives on a shelf-composited photo.)
- [x] `python -m pytest services/retrieval/tests/` still passes

#### Manual Verification

- [x] `participant_test.sh` from `eval.zip` runs to completion without errors against the updated service
- [x] `predictions.jsonl` contains a valid slug for all 3 organizer query images (no nulls)

---

## Testing Strategy

**Unit tests** (`services/retrieval/tests/test_catalog.py`):
- `extract_year` edge cases (ambiguous, absent, non-wine years like "1984" in a description)
- OCR year filter: pass-through, year match, fail-open
- `DinoIndex.search` returns correct owner indices for a synthetic 3-embedding case

**Integration tests** (none currently exist; add if time permits):
- Full pipeline: `SearchService.search(decoded_image)` returns a `ProductResult` with `status != "not_found"` for a clean reference image

**Eval script** (Phase 0):
- Run after each phase; record `Recall@1` in `reports/eval_YYYY-MM-DD-phaseN.json`

**Manual smoke tests** (after each phase):
- `docker compose up --build retrieval` starts clean
- `/health` returns ok
- `/v1/search` with a real wine photo from the eval zip returns a non-empty slug

---

## Performance Considerations

- **DINOv3 ONNX inference (ViT-S/16, 224px, CPU):** ~115 ms single-thread, ~20 ms at 16 threads. In a single-worker uvicorn the bottleneck is 115 ms per query. This replaces the FLANN search which is faster (~10 ms) but has lower recall. Net latency change: +~100 ms offset by removing OCR from cases where DINOv3 is already confident (OCR is ~200 ms).
- **Index size:** Adding `dino_embeddings` for 6000 references at 384 × float32 = 9.2 MB added to the `.npz`. Negligible.
- **Augmented index build time:** Current build ~90 s; with 3 augmented views and DINOv3 embedding ≈ +3.5 min. One-off; acceptable.
- **Brute-force cosine search:** `(6000, 384) @ (384,)` = 2.3M multiplies = ~0.1 ms. No ANN index needed.
- **ONNX runtime thread tuning:** Set `ort.SessionOptions` `intra_op_num_threads = os.cpu_count()` to use all available cores. Reduces inference to ~20–30 ms in the container.
- **ponytail:** mark the fixed `k=50` in `DinoIndex.search` with `# ponytail: k=50 fixed; increase to 100 if Recall@5 < 0.90 after Phase 3 eval`

---

## Migration Notes

- **Index rebuild required** after Phase 2 (augmentation) and Phase 3 (DINOv3 embeddings). Procedure: `docker compose stop retrieval retrieval-index && docker volume rm vinolog_retrieval-index && docker compose up -d retrieval-index retrieval`
- **Backward compatibility:** `SiftIndex.load` falls back to FLANN mode if `dino_embeddings` key is absent in `.npz`. Existing `sift-v2.npz` continues working with the new code during transition.
- **ONNX model file:** either bake into the Docker image (add a `RUN` in Dockerfile to download via `huggingface-cli`) or mount as a volume. Recommend baking to avoid runtime network dependency.
- **`INDEX_PATH` env var** currently points to `sift-v2.npz`; after augmented rebuild, bump to `sift-v3.npz` to avoid accidentally overwriting the working index before validation.

---

## References

- Analysis of current pipeline: prior conversation in this session (2026-09-16)
- DINOv3 paper: [arXiv:2508.10104](https://arxiv.org/abs/2508.10104)
- DINOv3 ONNX exports: [onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX](https://huggingface.co/onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX)
- DINOv3 license: [Meta DINOv3 License](https://ai.meta.com/resources/models-and-libraries/dinov3-license/) — commercial use permitted; "Built with DINOv3" attribution required
- Organizer eval format: `data/dataset/eval.zip` / `queries.tsv` + `participant_test.sh`
- Current pipeline entry points: `services/retrieval/app/index.py:78`, `service.py:22`, `ocr.py:20`
