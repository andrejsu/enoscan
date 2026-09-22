import pytest

from importer.mapping import Mapping, SourceImage
from importer.overrides import apply_overrides, parse_overrides


HEADER = ["slug", "action", "strapi_filename", "note"]
SOURCES = [
    SourceImage("a.webp", "a.webp", "sha-a", 10),
    SourceImage("b.webp", "b.webp", "sha-b", 10),
    SourceImage("dir/dup.webp", "dup.webp", "sha-d1", 10),
    SourceImage("other/dup.webp", "dup.webp", "sha-d2", 10),
]
AUTO = [
    Mapping("wine-a", "sha-a", "a.webp", "image_filename", 1.0),
    Mapping("wine-b", "sha-b", "b.webp", "fuzzy_filename", 0.8),
]
ACTIVE = {"wine-a", "wine-b", "wine-c"}


def overrides(*rows: list[str]):
    return parse_overrides([HEADER, *rows])


def test_set_assigns_manual_image_and_displaces_previous_owner() -> None:
    result, issues = apply_overrides(AUTO, overrides(["wine-c", "set", "a.webp", ""]), ACTIVE, SOURCES)

    by_slug = {m.slug: m for m in result}
    assert "wine-a" not in by_slug
    assert by_slug["wine-c"].mapping_kind == "manual"
    assert by_slug["wine-c"].review_status == "confirmed"
    assert issues[0].kind == "override_displaced"
    assert issues[0].slug == "wine-a"


def test_reject_removes_mapping() -> None:
    result, _ = apply_overrides(AUTO, overrides(["wine-b", "reject", "", "wrong bottle"]), ACTIVE, SOURCES)

    assert [m.slug for m in result] == ["wine-a"]


def test_confirm_keeps_mapping() -> None:
    result, _ = apply_overrides(AUTO, overrides(["wine-b", "confirm", "", ""]), ACTIVE, SOURCES)

    assert next(m for m in result if m.slug == "wine-b").review_status == "confirmed"


def test_unknown_slug_fails() -> None:
    with pytest.raises(SystemExit, match="line 2"):
        apply_overrides(AUTO, overrides(["missing", "reject", "", ""]), ACTIVE, SOURCES)


def test_ambiguous_filename_fails() -> None:
    with pytest.raises(SystemExit, match="ambiguous"):
        apply_overrides(AUTO, overrides(["wine-c", "set", "dup.webp", ""]), ACTIVE, SOURCES)


def test_unknown_filename_fails() -> None:
    with pytest.raises(SystemExit, match="not in the archive"):
        apply_overrides(AUTO, overrides(["wine-c", "set", "nope.webp", ""]), ACTIVE, SOURCES)


def test_two_actions_for_one_slug_fail() -> None:
    with pytest.raises(SystemExit, match="line 3"):
        overrides(["wine-a", "confirm", "", ""], ["wine-a", "reject", "", ""])


def test_set_requires_filename_and_known_action() -> None:
    with pytest.raises(SystemExit, match="requires"):
        overrides(["wine-a", "set", "", ""])
    with pytest.raises(SystemExit, match="unknown action"):
        overrides(["wine-a", "delete", "", ""])


def test_header_only_file_is_empty() -> None:
    assert overrides() == []
