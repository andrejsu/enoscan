import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_search import read_manifest, summarize


def test_metrics_keep_errors_in_denominator_and_separate_unlabelled():
    rows = [
        dict(expected_slug="a", slugs=["a"], status="matched", elapsed_ms=1),
        dict(expected_slug="b", error="broken", elapsed_ms=3),
        dict(expected_slug=None, slugs=["a"], status="matched", elapsed_ms=2),
        dict(slugs=["a"], status="matched", elapsed_ms=4),
    ]
    report = summarize(rows)
    assert report["accuracy_at_1"] == 0.5
    assert report["unknown_false_matched"] == 1
    assert report["matched_precision"] == 0.5
    assert report["unlabelled"] == 1
    assert report["errors"] == 1


def test_manifest_rejects_capture_group_leakage(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text("\n".join(json.dumps(dict(path="a.jpg", group="same", split=split)) for split in ("tuning", "holdout")))
    with pytest.raises(ValueError, match="leaks"):
        read_manifest(path)


def test_unlabelled_manifest_is_not_unknown(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(dict(path="a.jpg", group="one", split="pilot")))
    assert "expected_slug" not in read_manifest(path)[0]
