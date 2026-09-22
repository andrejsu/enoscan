#!/usr/bin/env python3
# Baseline on sift-v2.npz, 200 refs x 5 augmentations, seed 42 (2026-09-16, before Phase 2+):
#   Recall@1 = 0.958   Recall@5 = 0.996   Recall@10 = 0.996
#   blur 0.935 | jpeg 0.980 | perspective 0.975 | brightness 0.975 | combined 0.925
# Queries here are degraded copies of the indexed images, so this is a near-duplicate
# upper bound, not a prediction of organizer-eval accuracy on real photos.
#
# --profile hard, same index/refs/seed, 7 augmentations (2026-09-16):
#   Recall@1 = 0.832   Recall@5 = 0.875   Recall@10 = 0.876
#   hard_perspective 0.970 | crop_zoom 0.965 | motion_blur 0.840 | low_light 0.965
#   glare 0.970 | shelf 0.950 | hard_combined 0.165
# Recall@10 sits only 4.4 points above Recall@1: when the shortlist misses, it misses
# entirely, so the failure is in candidate selection rather than in reranking.
from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

_HERE = Path(__file__).resolve().parent
for _root in (_HERE.parent / "services" / "retrieval", _HERE.parent):
    if (_root / "app" / "index.py").exists():
        sys.path.insert(0, str(_root))
        break

from app.catalog import load_references  # noqa: I001
from app.config import load_settings
from app.index import SIFT_INDEX_KIND, SiftIndex
from app.index_store import current_index_path
from app.storage import IMAGES_BUCKET, ObjectStore
from eval_augmentations import PROFILES


def run_eval(samples: int, seed: int = 42, profile: str = "easy") -> None:
    database_url = load_settings().database_url
    store = ObjectStore()
    index = SiftIndex.load(str(current_index_path(database_url, SIFT_INDEX_KIND, store)))
    object_keys = {reference.image_sha256: reference.object_key for reference in load_references(database_url)}
    references = index.references

    rng = random.Random(seed)
    selected = rng.sample(references, min(samples, len(references)))

    augmentations = PROFILES[profile]
    aug_names = list(augmentations.keys())
    aug_fns: list[Callable[[np.ndarray], np.ndarray]] = [augmentations[n] for n in aug_names]  # type: ignore[assignment]
    n_refs = len(selected)
    n_augs = len(aug_names)
    total = n_refs * n_augs

    recall_at = {1: 0, 5: 0, 10: 0}
    aug_recall_at1: dict[str, int] = {n: 0 for n in aug_names}
    slowest: list[tuple[float, str, str]] = []

    for ref in selected:
        content = np.frombuffer(store.get_bytes(IMAGES_BUCKET, object_keys[ref.image_sha256]), dtype=np.uint8)
        img = cv2.imdecode(content, cv2.IMREAD_COLOR)
        if img is None:
            total -= n_augs
            continue

        for aug_name, aug_fn in zip(aug_names, aug_fns):
            aug_img = aug_fn(img)
            t0 = time.perf_counter()
            result = index.search(aug_img, limit=50)
            elapsed = (time.perf_counter() - t0) * 1000
            slowest.append((elapsed, ref.wine.slug, aug_name))

            found_at: int | None = None
            for rank, candidate in enumerate(result.candidates, 1):
                if candidate.wine.slug == ref.wine.slug:
                    found_at = rank
                    break

            if found_at is not None and found_at <= 1:
                recall_at[1] += 1
                aug_recall_at1[aug_name] += 1
            if found_at is not None and found_at <= 5:
                recall_at[5] += 1
            if found_at is not None and found_at <= 10:
                recall_at[10] += 1

    print(f"\n=== Eval Results [{profile}] ({n_refs} refs × {n_augs} augmentations = {total} queries) ===")
    print(f"Recall@1:  {recall_at[1] / total:.3f}  ({recall_at[1]}/{total})")
    print(f"Recall@5:  {recall_at[5] / total:.3f}  ({recall_at[5]}/{total})")
    print(f"Recall@10: {recall_at[10] / total:.3f}  ({recall_at[10]}/{total})")
    print("\nPer-augmentation Recall@1:")
    for name in aug_names:
        hits = aug_recall_at1[name]
        print(f"  {name:12s}: {hits / n_refs:.3f}  ({hits}/{n_refs})")

    slowest.sort(reverse=True)
    print("\nTop-5 slowest queries (ms):")
    for ms, slug, aug in slowest[:5]:
        print(f"  {ms:7.1f} ms  {slug}  [{aug}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Recall@K for the retrieval index")
    parser.add_argument("--samples", type=int, default=200, help="Number of references to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="easy",
                        help="easy: mild noise (recorded baseline); hard: shop-photo conditions")
    args = parser.parse_args()
    run_eval(args.samples, args.seed, args.profile)


if __name__ == "__main__":
    main()
