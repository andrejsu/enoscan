#!/usr/bin/env python3
"""Evaluate the complete SearchService; synthetic results are never real-photo accuracy."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/retrieval"))
from app.image_features import decode_image
from app.index import SiftIndex
from app.service import SearchService
from eval_augmentations import PROFILES


def summarize(rows: list[dict]) -> dict:
    known = [r for r in rows if r.get("expected_slug")]
    unknown = [r for r in rows if "expected_slug" in r and r["expected_slug"] is None]
    labelled = known + unknown
    matched = [r for r in labelled if r.get("status") == "matched"]
    def ratio(count: int, total: int):
        return count / total if total else None
    times = [r["elapsed_ms"] for r in rows]
    visual_known = [r for r in known if "visual_slugs" in r.get("diagnostics", {})]
    return {
        "count": len(rows), "known": len(known), "unknown": len(unknown),
        "unlabelled": len(rows) - len(labelled),
        "accuracy_at_1": ratio(sum(r.get("slugs", [None])[:1] == [r["expected_slug"]] for r in known), len(known)),
        "recall_at_5": ratio(sum(r["expected_slug"] in r.get("slugs", [])[:5] for r in known), len(known)),
        "visual_recall": ratio(sum(r["expected_slug"] in r["diagnostics"].get("visual_slugs", []) for r in visual_known), len(visual_known)),
        "matched_coverage": ratio(len(matched), len(labelled)),
        "matched_precision": ratio(sum(bool(r.get("expected_slug")) and r.get("slugs", [])[:1] == [r["expected_slug"]] for r in matched), len(matched)),
        "unknown_false_matched": ratio(sum(r.get("status") == "matched" for r in unknown), len(unknown)),
        "errors": sum("error" in r for r in rows),
        "p50_ms": float(np.percentile(times, 50)) if times else None,
        "p95_ms": float(np.percentile(times, 95)) if times else None,
    }


def read_manifest(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    groups = {}
    for row in rows:
        if not isinstance(row.get("path"), str) or row.get("split") not in {"tuning", "holdout", "pilot"}:
            raise ValueError("Each row needs path and split (tuning/holdout/pilot)")
        if not isinstance(row.get("group"), str) or not row["group"]:
            raise ValueError("Each row needs a capture-session group")
        if "expected_slug" in row and row["expected_slug"] is not None and (not isinstance(row["expected_slug"], str) or not row["expected_slug"]):
            raise ValueError("expected_slug must be a nonempty slug or null for unknown")
        previous = groups.setdefault(row["group"], row["split"])
        if previous != row["split"]:
            raise ValueError("Capture group leaks across splits")
        row["path"] = str((path.parent / row["path"]).resolve())
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--synthetic", type=int, metavar="REFERENCE_COUNT")
    parser.add_argument("--profile", choices=PROFILES, default="hard")
    parser.add_argument("--split", choices=["tuning", "holdout", "pilot"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--visual-limit", type=int, choices=range(1, 201), default=24, metavar="1..200")
    args = parser.parse_args()
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / "services/retrieval/app").glob("*.py")):
        source_hash.update(path.name.encode() + path.read_bytes())
    from app.catalog import current_dataset_version, load_references
    from app.config import load_settings
    from app.index import SIFT_INDEX_KIND
    from app.index_store import current_index_path
    from app.storage import IMAGES_BUCKET, ObjectStore

    database_url = load_settings().database_url
    store = ObjectStore()
    index_path = current_index_path(database_url, SIFT_INDEX_KIND, store)
    index = SiftIndex.load(str(index_path))
    dataset_version = current_dataset_version(database_url)
    service = SearchService(index, visual_limit=args.visual_limit, dataset_version=dataset_version)
    if args.manifest:
        entries = read_manifest(args.manifest)
        if args.split:
            entries = [r for r in entries if r["split"] == args.split]
    else:
        if args.synthetic < 1:
            parser.error("--synthetic must be positive")
        object_keys = {reference.image_sha256: reference.object_key for reference in load_references(database_url)}
        refs = random.Random(args.seed).sample(index.references, min(args.synthetic, len(index.references)))
        entries = [{"object_key": object_keys[ref.image_sha256],
                    "expected_slug": ref.wine.slug, "group": ref.wine.slug,
                    "split": "synthetic", "augmentation": aug} for ref in refs for aug in PROFILES[args.profile]]
    if not entries:
        parser.error("No queries selected")
    rows = []
    for entry in entries:
        started = time.perf_counter()
        row = dict(entry)
        try:
            content = (store.get_bytes(IMAGES_BUCKET, entry["object_key"]) if "object_key" in entry
                       else Path(entry["path"]).read_bytes())
            image = decode_image(content)
            if "augmentation" in entry:
                image = PROFILES[args.profile][entry["augmentation"]](image)
            prediction = service.search(image)
            body = prediction.body
            row.update(status=body["status"], slugs=[c["slug"] for c in body["candidates"]],
                       confidence=body["confidence"], timing=body["timing"], version=body["version"],
                       diagnostics=getattr(prediction, "diagnostics", {}))
        except Exception as error:
            # Evaluation records failures in the denominator; production does not swallow them.
            row["error"] = f"{type(error).__name__}: {error}"
        row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
        print(f"{len(rows)}/{len(entries)}", flush=True)
    report = {"label": args.label, "kind": "synthetic-near-duplicate" if args.synthetic else "manifest",
              "source_sha256": source_hash.hexdigest(), "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
              "dataset_version": dataset_version,
              "platform": platform.platform(), "processor": platform.processor(), "seed": args.seed,
              "cpu_count": os.cpu_count(), "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "first_query_ms": rows[0]["elapsed_ms"], "summary": summarize(rows),
              "by_group": {g: summarize([r for r in rows if r.get("augmentation", r["group"]) == g])
                           for g in sorted({r.get("augmentation", r["group"]) for r in rows})},
              "predictions": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    return bool(report["summary"]["errors"])


if __name__ == "__main__":
    sys.exit(main())
