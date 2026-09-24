import sys
sys.path.insert(0, "/app")

from pathlib import Path
import cv2

from app.catalog import current_dataset_version
from app.retriever_config import load_retriever_settings
from app.retriever_index import RETRIEVER_INDEX_KIND, RetrieverIndex
from app.embedding import EMBEDDING_MODEL, Dinov2Encoder
from app.embedding_store import EmbeddingStore
from app.index_store import fetch_index, require_build
from app.storage import ObjectStore
from app.label_normalize import Config as LabelConfig, prepare_query

FIXTURES = {
    "abrau-dyurso-russkoe-igristoe-polusuhoe-rozovoe-pino-nuar-12.webp": "abrau-dyurso-russkoe-igristoe-polusuhoe-rozovoe-pino-nuar-12",
    "balaklava-muskat-beloe-polusladkoe.webp": "balaklava-muskat-beloe-polusladkoe",
    "perovskih_polusuhoe_krasnoe.webp": "perovskih_polusuhoe_krasnoe",
    "yaiyla_кокур_hand.jpeg": "yaiyla-winery-kokur-kokur-belyy-beloe-suhoe-13",
    "zakat-denisov-vajneri.webp": "zakat-denisov-vajneri",
    "zhemchuzhnaya-9-aligote-czitron.webp": "zhemchuzhnaya-9-aligote-czitron",
}

settings = load_retriever_settings()
build = require_build(settings.database_url, RETRIEVER_INDEX_KIND, current_dataset_version(settings.database_url))
index = RetrieverIndex.load(str(fetch_index(ObjectStore(), build)))
embeddings = EmbeddingStore(settings.database_url, EMBEDDING_MODEL)
all_slugs = [reference.wine.slug for reference in index.references]
encoder = Dinov2Encoder(Path(settings.model_path), threads=8)
cfg = LabelConfig()

raw = {}
for fname, expected in FIXTURES.items():
    img = cv2.imread(f"/app/tests/fixtures/{fname}")
    prepared = prepare_query(img, segmenter=None, config=cfg, fast=True)
    qvec = encoder.encode_one(prepared.visual)
    emb_scores = embeddings.scores(build.id, qvec, all_slugs)
    emb_top = sorted(emb_scores, key=emb_scores.get, reverse=True)[:20]
    result = index.search(prepared.visual, limit=60, visual_limit=24, extra_slugs=tuple(emb_top))
    sift = {c.wine.slug: (c.score, c.inliers, c.good_matches) for c in result.candidates}
    raw[fname] = (sift, emb_scores, expected)
    print(f"captured {fname}: sift_candidates={len(sift)}", flush=True)

print("\n=== weight sweep ===")
best = None
for sift_w in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
    emb_w = 1.0 - sift_w
    correct = 0
    total = 0
    details = []
    for fname, (sift, emb_scores, expected) in raw.items():
        total += 1
        slugs = set(sift) | set(emb_scores)
        scored = []
        for slug in slugs:
            s, inl, good = sift.get(slug, (0.0, 0, 0))
            e = max(0.0, emb_scores.get(slug, 0.0))
            scored.append((sift_w * s + emb_w * e, slug, inl, good))
        scored.sort(reverse=True)
        top_slug = scored[0][1] if scored else None
        hit = top_slug == expected
        correct += hit
        details.append(f"{fname[:16]}:{'OK' if hit else top_slug[:20]}")
    print(f"sift={sift_w:.2f} emb={emb_w:.2f} -> {correct}/{total}  {details}")
    if best is None or correct > best[0]:
        best = (correct, sift_w)

print(f"\n=== best: sift={best[1]:.2f}, detail scores ===")
sift_w = best[1]
emb_w = 1.0 - sift_w
for fname, (sift, emb_scores, expected) in raw.items():
    slugs = set(sift) | set(emb_scores)
    scored = []
    for slug in slugs:
        s, inl, good = sift.get(slug, (0.0, 0, 0))
        e = max(0.0, emb_scores.get(slug, 0.0))
        scored.append((sift_w * s + emb_w * e, slug, inl, good))
    scored.sort(reverse=True)
    top2 = scored[:2]
    print(f"{fname}: expected={expected}")
    for score, slug, inl, good in top2:
        print(f"   {slug:50s} score={score:.4f} inliers={inl} good={good}")

print("\n=== status check at sift=0.45 (production threshold: inliers>=7, good>=10, score>=0.3, margin>=0.04) ===")
sift_w = 0.45
emb_w = 1.0 - sift_w
for fname, (sift, emb_scores, expected) in raw.items():
    slugs = set(sift) | set(emb_scores)
    scored = []
    for slug in slugs:
        s, inl, good = sift.get(slug, (0.0, 0, 0))
        e = max(0.0, emb_scores.get(slug, 0.0))
        scored.append((sift_w * s + emb_w * e, slug, inl, good))
    scored.sort(reverse=True)
    top_score, top_slug, top_inl, top_good = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = max(0.0, top_score - second_score)
    if top_inl >= 7 and top_good >= 10 and top_score >= 0.3 and margin >= 0.04:
        status = "matched"
    elif top_score >= 0.12:
        status = "uncertain"
    else:
        status = "not_found"
    hit = top_slug == expected
    print(f"{fname:55s} hit={hit} status={status:10s} score={top_score:.4f} margin={margin:.4f} inl={top_inl} good={top_good}")

print("\n=== status check at sift=0.60 (CURRENT LIVE DEFAULT) ===")
sift_w = 0.60
emb_w = 1.0 - sift_w
for fname, (sift, emb_scores, expected) in raw.items():
    slugs = set(sift) | set(emb_scores)
    scored = []
    for slug in slugs:
        s, inl, good = sift.get(slug, (0.0, 0, 0))
        e = max(0.0, emb_scores.get(slug, 0.0))
        scored.append((sift_w * s + emb_w * e, slug, inl, good))
    scored.sort(reverse=True)
    top_score, top_slug, top_inl, top_good = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = max(0.0, top_score - second_score)
    if top_inl >= 7 and top_good >= 10 and top_score >= 0.3 and margin >= 0.04:
        status = "matched"
    elif top_score >= 0.12:
        status = "uncertain"
    else:
        status = "not_found"
    hit = top_slug == expected
    print(f"{fname:55s} hit={hit} status={status:10s} score={top_score:.4f} margin={margin:.4f} inl={top_inl} good={top_good}")
