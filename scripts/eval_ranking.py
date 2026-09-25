#!/usr/bin/env python3
"""Score the scanner the way the TZ does, on photos with known answers.

Sends each labelled photo to the ranking service exactly like the organizer's
participant_test.sh (one at a time, `image` multipart field, 10 s limit) and
writes their predictions.jsonl. It also calls /v1/search for the top-5 and
the top-1/top-2 margin. `--predictions` scores an existing predictions.jsonl
from participant_test.sh instead, matching photos by SHA-256.

Metrics (in-catalog = row with an expected slug, out-of-catalog = empty one):
- match_rate — «доля совпадений»: the answer equals the expected slug, and an
  out-of-catalog photo counts as correct only when the answer is null.
- precision / recall / f1 — top-1 with abstention: precision over non-null
  answers, recall over in-catalog photos. With RANKING_EVAL_POLICY=top1 every
  photo is answered, so precision only drops on wrong and out-of-catalog ones.
- hit_at_1 / hit_at_5 — the expected wine is first / in the first five of
  /v1/search, whatever the decision; f1_at_5 counts an answered photo as a hit
  when the expected wine is anywhere in its top-5.
- margin — top-1 minus top-2 score, split by whether top-1 was right: the
  gap the TZ wants to be clear enough to skip the choice screen.
- latency — per eval request; the TZ target is 3 s, the organizer's curl gives
  up at 10 s and records null.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SLA_MS = 3000
ORGANIZER_TIMEOUT_S = 10


def read_labels(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].split("\t") != ["image_path", "expected_slug"]:
        raise ValueError("labels header must be: image_path<TAB>expected_slug")
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0]:
            raise ValueError(f"line {number}: expected image_path<TAB>expected_slug")
        rows.append({"image": (path.parent / parts[0]).resolve(), "expected_slug": parts[1].strip() or None})
    return rows


def post_image(url: str, image: Path, timeout: float) -> tuple[int | None, object, int]:
    """(HTTP status or None on timeout/network error, JSON body or None, ms)."""
    boundary = "vinolog-eval-boundary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{image.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + image.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, payload = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, payload = error.code, None
    except (urllib.error.URLError, TimeoutError):
        status, payload = None, None
    return status, payload, round((time.perf_counter() - started) * 1000)


def organizer_slug(status: int | None, payload: object) -> str | None:
    """Same parsing as participant_test.sh's jq filter."""
    if status not in (200, 201):
        return None
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    slug = payload.get("slug") if isinstance(payload, dict) else None
    return slug if isinstance(slug, str) and slug else None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(base: str, labels: list[dict]) -> list[dict]:
    rows = []
    for index, label in enumerate(labels, start=1):
        status, payload, latency_ms = post_image(f"{base}/v1/eval/predict", label["image"], ORGANIZER_TIMEOUT_S)
        _, product, _ = post_image(f"{base}/v1/search", label["image"], 60)
        product = product if isinstance(product, dict) else {}
        rows.append({
            "query_id": f"q-{index:06d}", "image_path": str(label["image"]), "image_sha256": sha256(label["image"]),
            "predicted_slug": organizer_slug(status, payload), "latency_ms": latency_ms,
            "expected_slug": label["expected_slug"], "status": product.get("status"),
            "top5": [candidate["slug"] for candidate in product.get("candidates", [])[:5]],
            "margin": product.get("confidence", {}).get("margin"),
        })
        print(f"{index}/{len(labels)} {label['image'].name}: {rows[-1]['predicted_slug']} ({latency_ms} ms)", file=sys.stderr)
    return rows


def attach_labels(predictions: list[dict], labels: list[dict]) -> list[dict]:
    expected = {sha256(label["image"]): label["expected_slug"] for label in labels}
    missing = [row["image_path"] for row in predictions if row["image_sha256"] not in expected]
    if missing:
        raise ValueError(f"no label for {len(missing)} predicted photo(s), e.g. {missing[0]}")
    return [{**row, "expected_slug": expected[row["image_sha256"]]} for row in predictions]


def _ratio(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


def summarize(rows: list[dict]) -> dict:
    known = [row for row in rows if row["expected_slug"]]
    unknown = [row for row in rows if not row["expected_slug"]]
    answered = [row for row in rows if row["predicted_slug"]]
    correct = [row for row in known if row["predicted_slug"] == row["expected_slug"]]
    precision, recall = _ratio(len(correct), len(answered)), _ratio(len(correct), len(known))
    ranked = [row for row in rows if "top5" in row]
    ranked_known = [row for row in ranked if row["expected_slug"]]
    hits5 = [row for row in ranked_known if row["predicted_slug"] and row["expected_slug"] in row["top5"]]
    precision5 = _ratio(len(hits5), sum(1 for row in ranked if row["predicted_slug"]))
    recall5 = _ratio(len(hits5), len(ranked_known))
    margins = {"correct": [], "wrong": []}
    for row in ranked:
        if row.get("margin") is not None and row["top5"]:
            margins["correct" if row["top5"][0] == row["expected_slug"] else "wrong"].append(row["margin"])
    latencies = sorted(row["latency_ms"] for row in rows)
    return {
        "photos": len(rows), "in_catalog": len(known), "out_of_catalog": len(unknown),
        "match_rate": _ratio(len(correct) + sum(1 for row in unknown if not row["predicted_slug"]), len(rows)),
        "precision": precision, "recall": recall, "f1": _f1(precision, recall),
        "answered": len(answered), "out_of_catalog_answered": sum(1 for row in unknown if row["predicted_slug"]),
        "hit_at_1": _ratio(sum(1 for row in ranked_known if row["top5"][:1] == [row["expected_slug"]]), len(ranked_known)),
        "hit_at_5": _ratio(sum(1 for row in ranked_known if row["expected_slug"] in row["top5"]), len(ranked_known)),
        "f1_at_5": _f1(precision5, recall5),
        "margin_median": {kind: round(statistics.median(values), 4) if values else None for kind, values in margins.items()},
        "latency_ms": {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))] if latencies else None,
            "max": latencies[-1] if latencies else None,
        },
        "within_sla": _ratio(sum(1 for value in latencies if value <= SLA_MS), len(latencies)),
        "organizer_timeouts": sum(1 for value in latencies if value >= ORGANIZER_TIMEOUT_S * 1000),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", type=Path, default=Path("configs/labeled-photos.tsv"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base", default="http://127.0.0.1:8080", help="ranking service URL")
    source.add_argument("--predictions", type=Path, help="score participant_test.sh output instead of calling the service")
    parser.add_argument("--out", type=Path, required=True, help="report JSON; organizer-format predictions go next to it")
    args = parser.parse_args()

    labels = read_labels(args.labels)
    missing = [str(label["image"]) for label in labels if not label["image"].is_file()]
    if missing:
        parser.error(f"{len(missing)} labelled photo(s) not found, e.g. {missing[0]} (see scripts/README.md)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.predictions:
        predictions = [json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
        rows = attach_labels(predictions, labels)
    else:
        rows = run(args.base.rstrip("/"), labels)
        organizer_keys = ("query_id", "image_path", "image_sha256", "predicted_slug", "latency_ms")
        args.out.with_suffix(".predictions.jsonl").write_text(
            "".join(json.dumps({key: row[key] for key in organizer_keys}, ensure_ascii=False) + "\n" for row in rows))
    report = {"labels": str(args.labels), "summary": summarize(rows), "rows": rows}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
