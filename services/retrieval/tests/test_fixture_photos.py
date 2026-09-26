"""Real photos against the running stack: the ranking route of this working
tree (app/ranking_main.py) with the live OCR and visual retriever services
and the imported catalog. Skipped when any of them is not reachable — run it
inside the compose network (README, «Python-тесты сервиса»).

The fixture folder says what the scan must do with a photo:
- green/  — the wine is in the catalog; the file name is its slug unless
  GREEN_SLUGS says otherwise. The scan must match exactly that wine.
- red/    — the wine is not in the catalog at all. The scan must not match
  and must recommend nothing.
- yellow/ — the wine is not in the catalog, but its winery or line is. The
  scan must not match and must recommend a wine of that winery.
red/ and yellow/ file names describe what the label shows, not a slug.
"""

from __future__ import annotations

from collections.abc import Iterator
import mimetypes
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import ranking_main


FIXTURES = Path(__file__).parent / "fixtures"

# Green photos whose file name is not the catalog slug.
GREEN_SLUGS = {
    "yaiyla_кокур_hand.jpeg": "yaiyla-winery-kokur-kokur-belyy-beloe-suhoe-13",
}

# Yellow photo -> the winery its first recommendation must come from, and
# optionally a wine that must be among the recommendations.
YELLOW = {
    "aya_purity_in_balance_2025.webp": ("AYA Organic Wine & Vineyards", None),
    "inkerman_каберне_сухое_красное.webp": ("Инкерманский ЗМВ", None),
    "velvet_season_fanagoria_мускат_сладкое.webp": ("Фанагория", "fanagoriya-velvet-season-muskat-ottonel-beloe-sladkoe-13"),
}


def _photos(folder: str) -> list[Path]:
    return sorted(path for path in (FIXTURES / folder).iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})


def _unreachable() -> str | None:
    settings = ranking_main.settings
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3):
            pass
    except psycopg.OperationalError as error:
        return f"PostgreSQL is not available: {error}"
    for name, base_url in (("OCR", settings.ocr_base_url), ("retriever", settings.retriever_base_url)):
        try:
            httpx.get(f"{base_url}/health", timeout=3).raise_for_status()
        except httpx.HTTPError as error:
            return f"{name} service at {base_url} is not available: {type(error).__name__}"
    return None


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    if reason := _unreachable():
        pytest.skip(reason)
    with TestClient(ranking_main.app) as client:
        yield client


def scan(client: TestClient, photo: Path) -> dict:
    content_type = mimetypes.guess_type(photo.name)[0] or "application/octet-stream"
    response = client.post("/v1/search", files={"image": (photo.name, photo.read_bytes(), content_type)})
    assert response.status_code == 200, response.text
    return response.json()


def describe(body: dict) -> str:
    top = [(c["slug"], c["score"]) for c in body["candidates"][:3]]
    return f"status={body['status']} margin={body['confidence']['margin']} top3={top}"


def test_every_yellow_photo_has_an_expectation():
    assert {photo.name for photo in _photos("yellow")} == set(YELLOW)


@pytest.mark.parametrize("photo", _photos("green"), ids=lambda path: path.name)
def test_catalog_wine_is_matched(client, photo):
    expected = GREEN_SLUGS.get(photo.name, photo.stem)
    assert expected in ranking_main.wines_by_slug, f"{expected} is not in the imported catalog"
    body = scan(client, photo)
    assert body["status"] == "matched" and body["wine"]["slug"] == expected, describe(body)
    assert body["recommendations"] == []


@pytest.mark.parametrize("photo", _photos("red"), ids=lambda path: path.name)
def test_wine_outside_the_catalog_is_not_matched_and_nothing_is_recommended(client, photo):
    body = scan(client, photo)
    assert body["status"] == "not_found", describe(body)
    assert body["wine"] is None
    assert body["recommendations"] == [], [(item["slug"], item["reason"]) for item in body["recommendations"]]


@pytest.mark.parametrize("photo", _photos("yellow"), ids=lambda path: path.name)
def test_wine_outside_the_catalog_is_not_matched_but_related_wines_are_recommended(client, photo):
    winery, expected_slug = YELLOW[photo.name]
    body = scan(client, photo)
    assert body["status"] == "not_found", describe(body)
    recommendations = body["recommendations"]
    assert recommendations, f"no recommendations; {describe(body)}"
    assert recommendations[0]["wine"]["producer"] == winery, [item["wine"]["producer"] for item in recommendations]
    if expected_slug:
        assert expected_slug in [item["slug"] for item in recommendations]
    assert all(item["reason"] and item["sharedFields"] for item in recommendations)
