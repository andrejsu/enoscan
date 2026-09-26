"""The one scan behind both routes of the ranking service, so their top-1 can
never diverge: the OCR service (app/ocr) and the visual retriever
(app/visual) concurrently, then one ranking pass (search/ranking.py).

Both producers are fetched over HTTP rather than loaded in-process: each
already runs as its own service, and holding a second copy of the DINOv2
index (~1.3-2.2GB) here was enough to push the compose stack into OOM
restart loops. A slow or unreachable producer degrades the scan to the
other one instead of failing it outright.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

import httpx

from ..catalog.models import Wine
from ..evidence import FieldCandidate, RetrievalFields, fields_from_json
from ..ocr.constants import SEARCH_TEXT_MIN_CONFIDENCE
from .config import SearchSettings
from .ranking import RankingResult, rank
from .recommendations import Recommendation, common_name_tokens, recommend


class ProducersUnavailable(RuntimeError):
    """Neither OCR nor the visual retriever answered: an outage, not «вино не найдено»."""


@dataclass(frozen=True)
class ProducerReply:
    """A producer's JSON (None when the call failed), why it failed, and how long it took."""
    payload: dict | None
    error: str | None
    ms: int


@dataclass(frozen=True)
class Scan:
    result: RankingResult
    ocr: ProducerReply
    ocr_fields: RetrievalFields
    ocr_text: str
    visual: ProducerReply
    visual_candidates: list[dict]
    visual_fields: RetrievalFields
    rank_ms: int
    total_ms: int


def ocr_search_text(payload: dict | None) -> str:
    """The OCR service's words as one line, as the OCR service itself searches them."""
    words = (payload or {}).get("words", [])
    return " ".join(w["text"] for w in words if w["confidence"] >= SEARCH_TEXT_MIN_CONFIDENCE)


def evaluation_slug(result: RankingResult, policy: str) -> str:
    """Slug for the organizer's script; an empty string is recorded as null.

    Under `top1` the answer is the best wine the label was checked against and
    does not contradict — never an unchecked one from below the rejected, and
    nothing when the label contradicts every checked wine."""
    if result.status == "matched" and result.slug:
        return result.slug
    if policy == "top1" and result.score > 0:
        passed = {check.slug for check in result.checks if not check.kind}
        if not result.checks:  # no label text: nothing to check, visual order decides
            return result.ranked(1)[0][0]
        return next((slug for slug, _ in result.ranked(len(result.evidence)) if slug in passed), "")
    return ""


class SearchService:
    def __init__(self, settings: SearchSettings, wines: list[Wine], dataset_version: str,
                 client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.dataset_version = dataset_version
        self.wines_by_slug = {wine.slug: wine for wine in wines}
        self._wines = list(self.wines_by_slug.values())
        self._common_tokens = common_name_tokens(self._wines)
        self._client = client

    async def scan(self, content: bytes, content_type: str | None, filename: str | None) -> Scan:
        started = time.perf_counter()
        files = {"image": (filename or "image", content, content_type or "application/octet-stream")}
        ocr, visual = await asyncio.gather(
            self._post_image(self.settings.ocr_base_url, self.settings.ocr_timeout, files),
            self._post_image(self.settings.retriever_base_url, self.settings.retriever_timeout, files),
        )
        if ocr.error and visual.error:
            raise ProducersUnavailable
        ocr_fields = fields_from_json(ocr.payload["fields"]) if ocr.payload else RetrievalFields()
        ocr_text = ocr_search_text(ocr.payload)
        visual_candidates = visual.payload.get("candidates", []) if visual.payload else []
        visual_fields = RetrievalFields(slug=tuple(FieldCandidate(c["slug"], c["score"]) for c in visual_candidates))

        rank_started = time.perf_counter()
        result = rank(ocr_fields, visual_fields, self._wines, min_margin=self.settings.min_margin, ocr_text=ocr_text)
        rank_ms = round((time.perf_counter() - rank_started) * 1000)
        return Scan(result, ocr, ocr_fields, ocr_text, visual, visual_candidates, visual_fields, rank_ms,
                    round((time.perf_counter() - started) * 1000))

    def recommend(self, scan: Scan) -> tuple[Recommendation, ...]:
        return recommend(scan.result, scan.ocr_fields, self.wines_by_slug, ocr_text=scan.ocr_text,
                         common_tokens=self._common_tokens)

    async def _post_image(self, base_url: str, timeout: float, files: dict) -> ProducerReply:
        started = time.perf_counter()
        try:
            response = await self._client.post(f"{base_url}/v1/search", files=files, timeout=timeout)
            response.raise_for_status()
            payload, error = response.json(), None
        except httpx.HTTPError as failure:
            payload, error = None, type(failure).__name__
        return ProducerReply(payload, error, round((time.perf_counter() - started) * 1000))
