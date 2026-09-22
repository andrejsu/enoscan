#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

_HERE = Path(__file__).resolve().parent
for _root in (_HERE.parent / "services" / "retrieval", _HERE.parent):
    if (_root / "app" / "index.py").exists():
        sys.path.insert(0, str(_root))
        break

import psycopg

from app.catalog import load_references
from app.config import load_settings
from app.storage import IMAGES_BUCKET, ObjectStore

OVERRIDES_HEADER = ["slug", "action", "strapi_filename", "note"]

IMAGENET_MEAN = np.float32([0.485, 0.456, 0.406]).reshape(3, 1, 1)
IMAGENET_STD = np.float32([0.229, 0.224, 0.225]).reshape(3, 1, 1)


def load_session(model_path: str) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = os.cpu_count() or 4
    return ort.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])


def preprocess(image: np.ndarray) -> np.ndarray:
    resized = cv2.resize(image, (224, 224), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return (rgb.transpose(2, 0, 1) - IMAGENET_MEAN) / IMAGENET_STD


def embed_objects(
    session: ort.InferenceSession,
    store: ObjectStore,
    keys: list[str],
    batch_size: int = 16,
    progress_label: str = "",
) -> tuple[np.ndarray, np.ndarray]:
    embeddings = np.zeros((len(keys), 384), dtype=np.float32)
    usable = np.zeros(len(keys), dtype=bool)
    pending: list[tuple[int, np.ndarray]] = []

    def flush() -> None:
        if not pending:
            return
        batch = np.stack([tensor for _, tensor in pending])
        output = session.run(["pooler_output"], {"pixel_values": batch})[0]
        for (position, _), vector in zip(pending, output):
            embeddings[position] = vector
            usable[position] = True
        pending.clear()

    for position, key in enumerate(keys):
        content = np.frombuffer(store.get_bytes(IMAGES_BUCKET, key), dtype=np.uint8)
        image = cv2.imdecode(content, cv2.IMREAD_COLOR)
        if image is not None:
            pending.append((position, preprocess(image)))
        if len(pending) >= batch_size:
            flush()
        if progress_label and position and position % 500 == 0:
            print(f"  {progress_label}: embedded {position}/{len(keys)}")
    flush()
    return embeddings, usable


def normalize_rows(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.maximum(norms, 1e-8)


def flag_suspicious(
    unit_embeddings: np.ndarray,
    usable: np.ndarray,
    wineries: list[str],
    mapping_kinds: list[str],
    threshold: float = 0.85,
) -> list[tuple[int, int, float]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for position, winery in enumerate(wineries):
        if usable[position]:
            groups[winery].append(position)

    flagged: list[tuple[int, int, float]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        block = unit_embeddings[members]
        cosine = block @ block.T
        np.fill_diagonal(cosine, -1.0)
        for row, position in enumerate(members):
            if mapping_kinds[position] != "fuzzy_filename":
                continue
            best = int(np.argmax(cosine[row]))
            score = float(cosine[row, best])
            if score > threshold:
                flagged.append((position, members[best], score))
    return flagged


def load_orphans(database_url: str) -> list[dict[str, object]]:
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT ON (i.sha256) i.sha256, i.object_key, s.strapi_path, s.filename, i.size_bytes
            FROM images i
            JOIN image_sources s ON s.image_sha256 = i.sha256
            WHERE NOT EXISTS (SELECT 1 FROM wine_images wi WHERE wi.image_sha256 = i.sha256)
            ORDER BY i.sha256, s.strapi_path
            """
        ).fetchall()
    return [
        {"sha256": sha, "object_key": key, "strapi_path": path, "filename": filename, "size_bytes": size}
        for sha, key, path, filename, size in rows
    ]


def overrides_rows(proposed_fixes: list[dict[str, object]]) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[str] = set()
    for fix in proposed_fixes:
        slug = str(fix["proposed_slug"])
        if slug in seen:
            continue
        seen.add(slug)
        rows.append([slug, "set", str(fix["filename"]), f"audit cosine={fix['cosine']}"])
    return rows


def run_audit(
    model_path: str,
    output_dir: str,
    orphan_threshold: float = 0.90,
) -> Path:
    settings = load_settings()
    store = ObjectStore()
    references = load_references(settings.database_url)
    session = load_session(model_path)
    print(f"Loaded {len(references)} mapped references.")

    reference_embeddings, reference_usable = embed_objects(
        session,
        store,
        [reference.object_key for reference in references],
        progress_label="references",
    )
    unit_references = normalize_rows(reference_embeddings)
    print(f"Embedded {int(reference_usable.sum())}/{len(references)} reference images.")

    flagged = flag_suspicious(
        unit_references,
        reference_usable,
        [reference.wine.winery for reference in references],
        [reference.mapping_kind for reference in references],
    )
    suspicious = [
        {
            "slug": references[position].wine.slug,
            "name": references[position].wine.name,
            "winery": references[position].wine.winery,
            "image_sha256": references[position].image_sha256,
            "mapping_kind": references[position].mapping_kind,
            "mapping_score": round(references[position].mapping_score, 4),
            "nearest_peer_slug": references[peer].wine.slug,
            "nearest_peer_sha256": references[peer].image_sha256,
            "cosine": round(score, 4),
        }
        for position, peer, score in sorted(flagged, key=lambda item: item[2], reverse=True)
    ]

    orphan_media = load_orphans(settings.database_url)
    print(f"Found {len(orphan_media)} orphaned original images.")

    orphan_embeddings, orphan_usable = embed_objects(
        session,
        store,
        [str(item["object_key"]) for item in orphan_media],
        progress_label="orphans",
    )
    unit_orphans = normalize_rows(orphan_embeddings)

    proposed_fixes = []
    if len(orphan_media) and reference_usable.any():
        valid_reference_positions = np.flatnonzero(reference_usable)
        cosine = unit_orphans @ unit_references[valid_reference_positions].T
        for position, item in enumerate(orphan_media):
            if not orphan_usable[position]:
                continue
            best = int(np.argmax(cosine[position]))
            if float(cosine[position, best]) < orphan_threshold:
                continue
            reference = references[int(valid_reference_positions[best])]
            proposed_fixes.append({
                "strapi_path": item["strapi_path"],
                "filename": item["filename"],
                "proposed_slug": reference.wine.slug,
                "proposed_name": reference.wine.name,
                "proposed_winery": reference.wine.winery,
                "cosine": round(float(cosine[position, best]), 4),
            })
        proposed_fixes.sort(key=lambda item: item["cosine"], reverse=True)

    report = {
        "generated_at": datetime.now(UTC).date().isoformat(),
        "reference_count": len(references),
        "embedded_reference_count": int(reference_usable.sum()),
        "suspicious": suspicious,
        "orphaned": [
            {"strapi_path": item["strapi_path"], "filename": item["filename"], "size_bytes": item["size_bytes"]}
            for item in orphan_media
        ],
        "proposed_fixes": proposed_fixes,
    }

    destination = Path(output_dir) / f"mapping_audit_{report['generated_at']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    overrides_path = Path(output_dir) / "image-overrides-proposed.csv"
    with overrides_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(OVERRIDES_HEADER)
        writer.writerows(overrides_rows(proposed_fixes))

    print(f"\nSuspicious fuzzy mappings: {len(suspicious)}")
    print(f"Orphaned media: {len(report['orphaned'])}")
    print(f"Proposed fixes: {len(proposed_fixes)}")
    print(f"Report written to {destination}")
    print(f"Proposed overrides written to {overrides_path}; review and copy rows into db/image-overrides.csv")
    return destination


def self_check() -> None:
    same = np.float32([1.0, 0.0, 0.0])
    near = np.float32([0.99, 0.14, 0.0])
    far = np.float32([0.0, 1.0, 0.0])
    embeddings = normalize_rows(np.stack([same, near, far]))
    usable = np.array([True, True, True])

    flagged = flag_suspicious(
        embeddings, usable,
        ["Табия", "Табия", "Табия"],
        ["fuzzy_filename", "image_filename", "fuzzy_filename"],
    )
    flagged_positions = {position for position, _, _ in flagged}
    assert flagged_positions == {0}, flagged

    other_winery = flag_suspicious(
        embeddings, usable,
        ["Табия", "Фанагория", "Табия"],
        ["fuzzy_filename", "image_filename", "fuzzy_filename"],
    )
    assert not other_winery, other_winery

    skipped = flag_suspicious(
        embeddings, usable,
        ["Табия", "Табия", "Табия"],
        ["image_filename", "image_filename", "image_filename"],
    )
    assert not skipped, skipped

    unusable = flag_suspicious(
        embeddings, np.array([True, False, True]),
        ["Табия", "Табия", "Табия"],
        ["fuzzy_filename", "image_filename", "fuzzy_filename"],
    )
    assert not unusable, unusable

    rows = overrides_rows([
        {"proposed_slug": "tabiya-pino", "filename": "a.webp", "cosine": 0.97},
        {"proposed_slug": "tabiya-pino", "filename": "b.webp", "cosine": 0.93},
        {"proposed_slug": "tabiya-kokur", "filename": "c.webp", "cosine": 0.91},
    ])
    assert rows == [
        ["tabiya-pino", "set", "a.webp", "audit cosine=0.97"],
        ["tabiya-kokur", "set", "c.webp", "audit cosine=0.91"],
    ], rows

    print("self-check passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit catalog to image mapping with DINOv3 cosine")
    parser.add_argument("--model", default="/models/dinov3-vits16/model.onnx")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--orphan-threshold", type=float, default=0.90,
                        help="Minimum cosine for an orphan reassignment to be proposed")
    parser.add_argument("--self-check", action="store_true", help="Run flagging assertions and exit")
    args = parser.parse_args()

    if args.self_check:
        self_check()
        return
    run_audit(args.model, args.out, args.orphan_threshold)


if __name__ == "__main__":
    main()
