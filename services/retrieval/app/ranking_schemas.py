"""Response schemas of the ranking service (app/ranking_main.py) for its
OpenAPI / Swagger page (/docs). They mirror apps/web's #shared/contracts
ScanResponse — change both together. The per-stage `debug` trace is left
as a free-form object: it exists for the result page's debug panel only
and follows ScanDebug in the web contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WineCard(BaseModel):
    slug: str
    name: str
    producer: str
    year: int | None = Field(description="Vintage from the catalog name; null when the name has none.")
    category: str | None
    color: str | None = Field(description="Catalog tasting notes on colour, free text.")
    region: str | None
    grapeVarieties: list[str]
    description: str | None
    servingTemperature: str | None
    imageUrl: str | None
    imagePreviewUrl: str | None


class ScanCandidate(BaseModel):
    slug: str
    score: float = Field(description="Ranking evidence: the wine's share of the full support, 0..1. Not a probability.")
    wine: WineCard


class ScanConfidence(BaseModel):
    kind: Literal["similarity", "calibrated_probability"]
    top1Score: float = Field(description="Score of the top-1 wine, whether or not it matched.")
    margin: float = Field(description="Top-1 minus top-2 score among wines the label does not contradict; "
                                      "`matched` needs at least RANKING_MIN_MARGIN.")


class ScanTiming(BaseModel):
    totalMs: int
    stages: dict[str, int] = Field(description="Per producer: `ocr`, `visual`, in ms.")


class ScanVersion(BaseModel):
    model: str
    catalog: str = Field(description="Dataset version of the last successful catalog import.")
    configuration: str


class ScanRecommendation(BaseModel):
    slug: str
    score: float = Field(description="Ranking evidence, the same scale as candidates[].score.")
    wine: WineCard
    sharedFields: list[Literal["name", "winery", "grape_varieties", "category", "sweetness", "region", "year"]] = \
        Field(description="What the wine has in common with the label.")
    reason: str = Field(description="Human-readable, e.g. «Та же винодельня «Фанагория», Красное».")
    difference: str | None = Field(description="What the label contradicts in this wine; null when nothing.")


class ScanResponse(BaseModel):
    status: Literal["matched", "uncertain", "not_found"]
    wine: WineCard | None = Field(description="The matched wine; null unless status is `matched`.")
    candidates: list[ScanCandidate] = Field(description="Top-5 by score; rejected wines go last.")
    confidence: ScanConfidence
    timing: ScanTiming
    alternatives: list[WineCard] = Field(description="Candidates 2-4, as cards.")
    recommendations: list[ScanRecommendation] = Field(
        description="Related catalog wines (same winery, line or grape) when the scan did not match; "
                    "empty when it did or when the label ties it to nothing in particular.")
    version: ScanVersion
    guidance: str | None = Field(default=None, description="What to do next; only when not matched.")
    debug: dict[str, Any] | None = Field(
        default=None, description="Per-stage trace (web contract ScanDebug); only with RANKING_DEBUG=true.")
    isMock: bool


class EvaluationPrediction(BaseModel):
    slug: str = Field(description="Top-1 catalog slug. Empty string when there is no confident answer under "
                                  "RANKING_EVAL_POLICY=matched; participant_test.sh records it as null.")


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "loading"]


UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Пустое поле `image`."},
    413: {"model": ErrorResponse, "description": "Файл больше MAX_UPLOAD_BYTES (10 МБ по умолчанию)."},
    415: {"model": ErrorResponse, "description": "Тип файла не JPEG, PNG, WebP или application/octet-stream."},
    422: {"model": ErrorResponse, "description": "Файл не декодируется как изображение или нет поля `image`."},
    503: {"model": ErrorResponse, "description": "Индекс ещё загружается или недоступны и OCR, и визуальный "
                                                 "ретривер. Это не «вино не найдено»."},
}
