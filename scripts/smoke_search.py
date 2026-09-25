#!/usr/bin/env python3
"""Local HTTP contract smoke; unlabelled photos do not measure identification accuracy."""
import argparse
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def request(base, route, content, mime):
    boundary = "vinolog-smoke-boundary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="photo"\r\n'
            f'Content-Type: {mime}\r\n\r\n').encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + route, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--archive", type=Path, default=Path("data/dataset/eval.zip"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    with zipfile.ZipFile(args.archive) as archive:
        for name in sorted(n for n in archive.namelist() if n.startswith("queries/") and n.endswith((".jpg", ".webp", ".png"))):
            content = archive.read(name)
            mime = "image/webp" if name.endswith(".webp") else "image/jpeg"
            started = time.perf_counter()
            status, product = request(args.base, "/v1/search", content, mime)
            eval_status, evaluation = request(args.base, "/v1/eval/predict", content, mime)
            top = product.get("candidates", [{}])[0].get("slug", "") if product.get("candidates") else ""
            assert status == eval_status == 200, (name, status, eval_status)
            # Unsure scans may be left empty under RANKING_EVAL_POLICY=matched.
            allowed = [{"slug": top}] if product["status"] == "matched" else [{"slug": top}, {"slug": ""}]
            assert evaluation in allowed, (name, evaluation, top)
            assert product["confidence"]["kind"] == "similarity"
            assert "diagnostics" not in product
            rows.append({"photo": name, "status": product["status"], "slug": top,
                         "product_and_eval_agree": True, "two_requests_ms": round((time.perf_counter() - started) * 1000)})
    errors = []
    for content, mime, expected in [(b"broken", "image/jpeg", 422), (b"broken", "text/plain", 415), (b"", "image/jpeg", 400)]:
        status, _ = request(args.base, "/v1/search", content, mime)
        assert status == expected, (status, expected)
        errors.append(status)
    report = {"kind": "unlabelled-http-smoke", "predictions": rows, "invalid_upload_statuses": errors,
              "accuracy": None, "note": "No ground-truth slugs; only contracts and successful processing checked."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
