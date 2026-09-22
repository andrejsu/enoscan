import pytest

from importer.catalog_csv import COLUMNS, parse_rows


def row(**values: str) -> dict[str, str]:
    base = {column: "" for column in COLUMNS}
    base.update({
        "Название вина": " Пино Нуар 2020 ",
        "Винодельня": "Табия",
        "Slug": "pino-nuar-2020",
        "Сорт винограда": "Пино Нуар, , Мерло",
        "Название фото": "DSC00836.webp",
    })
    base.update(values)
    return base


def test_cleans_values_and_splits_grapes() -> None:
    result = parse_rows([row(**{"Описание": "   "})])

    wine = result.wines[0]
    assert wine.name == "Пино Нуар 2020"
    assert wine.description is None
    assert wine.grape_varieties == ("Пино Нуар", "Мерло")
    assert wine.source_row_no == 1
    assert wine.raw_record_count == 1
    assert result.issues == []


def test_first_duplicate_wins_and_is_reported() -> None:
    result = parse_rows([
        row(**{"Описание": "первое"}),
        row(**{"Slug": "other"}),
        row(**{"Описание": "второе"}),
    ])

    wine = next(item for item in result.wines if item.slug == "pino-nuar-2020")
    assert wine.description == "первое"
    assert wine.raw_record_count == 2
    issue = next(item for item in result.issues if item.kind == "duplicate_slug")
    assert issue.detail == {"row_numbers": [1, 3], "payload_differs": True}


def test_identical_duplicates_are_marked_as_equal() -> None:
    result = parse_rows([row(), row()])

    assert result.issues[0].detail["payload_differs"] is False


def test_missing_slug_is_reported_and_skipped() -> None:
    result = parse_rows([row(**{"Slug": "  "})])

    assert result.wines == []
    assert result.issues[0].kind == "missing_slug"
    assert len(result.raw_rows) == 1


def test_header_whitespace_is_ignored() -> None:
    source = {f" {key} ": value for key, value in row().items()}

    assert parse_rows([source]).wines[0].slug == "pino-nuar-2020"


def test_missing_column_fails() -> None:
    source = row()
    del source["Slug"]

    with pytest.raises(SystemExit, match="Slug"):
        parse_rows([source])
