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
import pytesseract

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
    union_known = [r for r in known if "union_slugs" in r.get("diagnostics", {})]
    return {
        "count": len(rows), "known": len(known), "unknown": len(unknown),
        "unlabelled": len(rows) - len(labelled),
        "accuracy_at_1": ratio(sum(r.get("slugs", [None])[:1] == [r["expected_slug"]] for r in known), len(known)),
        "recall_at_5": ratio(sum(r["expected_slug"] in r.get("slugs", [])[:5] for r in known), len(known)),
        "union_recall": ratio(sum(r["expected_slug"] in r["diagnostics"]["union_slugs"] for r in union_known), len(union_known)),
        "visual_recall": ratio(sum(r["expected_slug"] in r["diagnostics"].get("visual_slugs", []) for r in union_known), len(union_known)),
        "matched_coverage": ratio(len(matched), len(labelled)),
        "matched_precision": ratio(sum(bool(r.get("expected_slug")) and r.get("slugs", [])[:1] == [r["expected_slug"]] for r in matched), len(matched)),
        "unknown_false_matched": ratio(sum(r.get("status") == "matched" for r in unknown), len(unknown)),
        "errors": sum("error" in r for r in rows),
        "ocr_fallbacks": sum(bool(r.get("diagnostics", {}).get("ocr", {}).get("error")) for r in rows),
        "p50_ms": float(np.percentile(times, 50)) if times else None,
        "p95_ms": float(np.percentile(times, 95)) if times else None,
        "fields": {field: field_metrics(rows, field) for field in ("year", "abv")},
    }


def field_metrics(rows: list[dict], field: str) -> dict:
    labelled = [r for r in rows if f"expected_{field}" in r]
    def value(row):
        evidence = row.get("diagnostics", {}).get("ocr", {}).get(field)
        return evidence["value"] if evidence else None
    extracted = [r for r in labelled if value(r) is not None]
    return {"labelled": len(labelled), "extracted": len(extracted),
            "precision": sum(value(r) == r[f"expected_{field}"] for r in extracted) / len(extracted) if extracted else None,
            "exact_including_abstention": sum(value(r) == r[f"expected_{field}"] for r in labelled) / len(labelled) if labelled else None}


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
    parser.add_argument("--index", required=True)
    parser.add_argument("--dataset", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--synthetic", type=int, metavar="REFERENCE_COUNT")
    parser.add_argument("--profile", choices=PROFILES, default="hard")
    parser.add_argument("--split", choices=["tuning", "holdout", "pilot"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--psm", type=int, choices=[6, 11], default=6)
    parser.add_argument("--raw", action="store_true", help="Disable grayscale/CLAHE")
    parser.add_argument("--retry", action="store_true", help="Retry one doubtful numeric line within OCR timeout")
    parser.add_argument("--ocr-timeout", type=float, default=2.0)
    parser.add_argument("--visual-limit", type=int, choices=range(1, 201), default=24, metavar="1..200")
    parser.add_argument("--full-catalog", action="store_true", help="Load catalog using DATABASE_URL or PG* environment")
    args = parser.parse_args()
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / "services/retrieval/app").glob("*.py")):
        source_hash.update(path.name.encode() + path.read_bytes())
    index = SiftIndex.load(args.index)
    options = dict(ocr_timeout=args.ocr_timeout, ocr_psm=args.psm, ocr_preprocess=not args.raw,
                   ocr_retry=args.retry, visual_limit=args.visual_limit)
    if args.full_catalog:
        from app.catalog import load_catalog
        from app.config import load_settings
        service = SearchService(index, catalog=load_catalog(load_settings().database_url)[0], **options)
    else:
        service = SearchService(index, **options)
    if args.manifest:
        entries = read_manifest(args.manifest)
        if args.split:
            entries = [r for r in entries if r["split"] == args.split]
    else:
        if args.synthetic < 1:
            parser.error("--synthetic must be positive")
        refs = random.Random(args.seed).sample(index.references, min(args.synthetic, len(index.references)))
        entries = [{"path": str(Path(args.dataset) / "uploads" / ref.relative_path),
                    "expected_slug": ref.wine.slug, "group": ref.wine.slug,
                    "split": "synthetic", "augmentation": aug} for ref in refs for aug in PROFILES[args.profile]]
    if not entries:
        parser.error("No queries selected")
    rows = []
    for entry in entries:
        started = time.perf_counter()
        row = dict(entry)
        try:
            image = decode_image(Path(entry["path"]).read_bytes())
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
              "source_sha256": source_hash.hexdigest(), "index_sha256": hashlib.sha256(Path(args.index).read_bytes()).hexdigest(),
              "tesseract": str(pytesseract.get_tesseract_version()), "languages": pytesseract.get_languages(),
              "platform": platform.platform(), "processor": platform.processor(), "seed": args.seed,
              "cpu_count": os.cpu_count(), "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "ocr_options": options,
              "catalog_scope": "database" if args.full_catalog else "indexed-only",
              "catalog_sha256": hashlib.sha256(json.dumps([vars(w) for w in service.text_search.wines.values()], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
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
