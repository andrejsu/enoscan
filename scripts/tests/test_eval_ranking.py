import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_ranking import attach_labels, organizer_slug, read_labels, sha256, summarize


def row(expected, predicted, top5=None, margin=0.1, latency_ms=1000):
    return dict(expected_slug=expected, predicted_slug=predicted, top5=top5 if top5 is not None else [predicted] if predicted else [],
                margin=margin, latency_ms=latency_ms)


def test_out_of_catalog_counts_as_matched_only_when_left_unanswered():
    report = summarize([row("a", "a"), row(None, None), row(None, "b")])
    assert report["match_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["out_of_catalog_answered"] == 1


def test_abstaining_lowers_recall_but_not_precision():
    report = summarize([row("a", "a"), row("b", None, top5=["b"]), row("c", "x", top5=["x", "c"])])
    assert report["precision"] == 0.5
    assert report["recall"] == pytest.approx(1 / 3, abs=1e-4)
    assert report["f1"] == 0.4
    assert report["hit_at_1"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["hit_at_5"] == 1.0


def test_margin_is_split_by_whether_top1_was_right():
    report = summarize([row("a", "a", margin=0.3), row("b", "x", top5=["x", "b"], margin=0.02)])
    assert report["margin_median"] == {"correct": 0.3, "wrong": 0.02}


def test_latency_reports_sla_share_and_organizer_timeouts():
    report = summarize([row("a", "a", latency_ms=900), row("b", None, latency_ms=10000)])
    assert report["within_sla"] == 0.5
    assert report["organizer_timeouts"] == 1
    assert report["latency_ms"]["max"] == 10000


def test_organizer_slug_parses_like_participant_script():
    assert organizer_slug(200, {"slug": "a"}) == "a"
    assert organizer_slug(200, [{"slug": "a"}]) == "a"
    assert organizer_slug(200, {"slug": ""}) is None
    assert organizer_slug(503, {"slug": "a"}) is None
    assert organizer_slug(None, None) is None


def test_labels_resolve_paths_and_empty_slug_means_out_of_catalog(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"a")
    labels = tmp_path / "labels.tsv"
    labels.write_text("image_path\texpected_slug\na.jpg\tkokur\na.jpg\t\n")
    rows = read_labels(labels)
    assert rows[0] == {"image": (tmp_path / "a.jpg").resolve(), "expected_slug": "kokur"}
    assert rows[1]["expected_slug"] is None


def test_labels_reject_a_wrong_header(tmp_path):
    labels = tmp_path / "labels.tsv"
    labels.write_text("query_id\timage_path\n")
    with pytest.raises(ValueError, match="header"):
        read_labels(labels)


def test_existing_predictions_are_matched_to_labels_by_sha256(tmp_path):
    image = tmp_path / "a.jpg"
    image.write_bytes(b"photo")
    labels = [{"image": image, "expected_slug": "kokur"}]
    predictions = [{"image_path": "renamed.jpg", "image_sha256": sha256(image), "predicted_slug": "kokur", "latency_ms": 5}]
    assert attach_labels(predictions, labels)[0]["expected_slug"] == "kokur"
    with pytest.raises(ValueError, match="no label"):
        attach_labels([{**predictions[0], "image_sha256": "other"}], labels)
