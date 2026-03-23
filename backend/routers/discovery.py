from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from models import SignalType
from services.signal_lab_service import SignalLabService

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryCandidateResponse(BaseModel):
    """Locally ranked discovery candidate with risk and scorecard context."""

    symbol: str
    name: str
    asset_type: str
    exchange: Optional[str]
    signal_type: SignalType
    strength: float
    composite_score: float
    risk_bucket: Literal["low", "medium", "high"]
    risk_score: float
    risk_fit_score: float
    volatility_pct: Optional[float]
    sentiment_score: Optional[float]
    mentions_1h: int
    latest_price: Optional[float]
    historical_hit_rate_pct: Optional[float]
    historical_avg_return_pct: Optional[float]
    discovery_score: float
    reasoning: str
    created_at: str


class DiscoveryAttemptResponse(BaseModel):
    """Diagnostics for one discovery AI attempt."""

    model: Optional[str]
    status: str
    status_code: Optional[int]
    message: str
    response_excerpt: Optional[str]


class DiscoveryAiPickResponse(BaseModel):
    """AI-refined discovery pick."""

    symbol: str
    action: str
    thesis: str
    risk_note: str
    confidence: Optional[float]


class DiscoverySearchRequest(BaseModel):
    """Payload for manual Sonar discovery searches."""

    query: str = Field(min_length=1, max_length=500)
    risk_profile: Literal["low", "balanced", "high"] = "balanced"
    direction: Literal["all", "buy", "sell"] = "buy"
    asset_type: Literal["all", "stock", "crypto"] = "all"
    horizon: Literal["24h", "72h", "7d"] = "72h"
    limit: int = Field(default=10, ge=1, le=20)


class DiscoverySearchResponse(BaseModel):
    """Combined local and AI-assisted discovery response."""

    status: Literal["success", "partial", "error"]
    query: str
    risk_profile: Literal["low", "balanced", "high"]
    direction: Literal["all", "buy", "sell"]
    asset_type: Literal["all", "stock", "crypto"]
    horizon: Literal["24h", "72h", "7d"]
    provider: str
    primary_model: str
    validation_model: Optional[str]
    used_model: Optional[str]
    market_summary: Optional[str]
    local_candidates: List[DiscoveryCandidateResponse]
    ai_summary: Optional[str]
    candidates: List[DiscoveryAiPickResponse]
    attempts: List[DiscoveryAttemptResponse]
    errors: List[DiscoveryAttemptResponse]
    raw_response: Optional[str]


@router.get("/candidates", response_model=List[DiscoveryCandidateResponse])
async def get_discovery_candidates(
    risk_profile: Literal["low", "balanced", "high"] = Query(default="balanced"),
    direction: Literal["all", "buy", "sell"] = Query(default="buy"),
    asset_type: Literal["all", "stock", "crypto"] = Query(default="all"),
    horizon: Literal["24h", "72h", "7d"] = Query(default="72h"),
    limit: int = Query(default=10, ge=1, le=25),
) -> List[DiscoveryCandidateResponse]:
    """Return risk-aware local candidates ranked for discovery workflows."""
    service = SignalLabService()
    try:
        rows = await service.get_discovery_candidates(
            risk_profile=risk_profile,
            direction=direction,
            asset_type=asset_type,
            horizon=horizon,
            limit=limit,
        )
    finally:
        await service.close()
    return [
        DiscoveryCandidateResponse(
            symbol=str(item["symbol"]),
            name=str(item["name"]),
            asset_type=str(item["asset_type"]),
            exchange=str(item["exchange"]) if item["exchange"] is not None else None,
            signal_type=item["signal_type"],
            strength=float(item["strength"]),
            composite_score=float(item["composite_score"]),
            risk_bucket=item["risk_bucket"],
            risk_score=float(item["risk_score"]),
            risk_fit_score=float(item["risk_fit_score"]),
            volatility_pct=float(item["volatility_pct"]) if item["volatility_pct"] is not None else None,
            sentiment_score=float(item["sentiment_score"]) if item["sentiment_score"] is not None else None,
            mentions_1h=int(item["mentions_1h"]),
            latest_price=float(item["latest_price"]) if item["latest_price"] is not None else None,
            historical_hit_rate_pct=(
                float(item["historical_hit_rate_pct"]) if item["historical_hit_rate_pct"] is not None else None
            ),
            historical_avg_return_pct=(
                float(item["historical_avg_return_pct"]) if item["historical_avg_return_pct"] is not None else None
            ),
            discovery_score=float(item["discovery_score"]),
            reasoning=str(item["reasoning"]),
            created_at=item["created_at"].isoformat(),
        )
        for item in rows
    ]


@router.post("/search", response_model=DiscoverySearchResponse)
async def run_discovery_search(payload: DiscoverySearchRequest) -> DiscoverySearchResponse:
    """Run Sonar discovery on top of local signal, risk and news context."""
    service = SignalLabService()
    try:
        result = await service.run_discovery_search(
            query=payload.query,
            risk_profile=payload.risk_profile,
            direction=payload.direction,
            asset_type=payload.asset_type,
            horizon=payload.horizon,
            limit=payload.limit,
        )
    finally:
        await service.close()

    local_candidates = [
        DiscoveryCandidateResponse(
            symbol=str(item["symbol"]),
            name=str(item["name"]),
            asset_type=str(item["asset_type"]),
            exchange=str(item["exchange"]) if item["exchange"] is not None else None,
            signal_type=item["signal_type"],
            strength=float(item["strength"]),
            composite_score=float(item["composite_score"]),
            risk_bucket=item["risk_bucket"],
            risk_score=float(item["risk_score"]),
            risk_fit_score=float(item["risk_fit_score"]),
            volatility_pct=float(item["volatility_pct"]) if item["volatility_pct"] is not None else None,
            sentiment_score=float(item["sentiment_score"]) if item["sentiment_score"] is not None else None,
            mentions_1h=int(item["mentions_1h"]),
            latest_price=float(item["latest_price"]) if item["latest_price"] is not None else None,
            historical_hit_rate_pct=(
                float(item["historical_hit_rate_pct"]) if item["historical_hit_rate_pct"] is not None else None
            ),
            historical_avg_return_pct=(
                float(item["historical_avg_return_pct"]) if item["historical_avg_return_pct"] is not None else None
            ),
            discovery_score=float(item["discovery_score"]),
            reasoning=str(item["reasoning"]),
            created_at=item["created_at"].isoformat(),
        )
        for item in result["local_candidates"]
    ]
    ai_candidates = [
        DiscoveryAiPickResponse(
            symbol=str(item["symbol"]),
            action=str(item["action"]),
            thesis=str(item["thesis"]),
            risk_note=str(item["risk_note"]),
            confidence=float(item["confidence"]) if item["confidence"] is not None else None,
        )
        for item in result["candidates"]
    ]
    attempts = [
        DiscoveryAttemptResponse(
            model=str(item["model"]) if item["model"] is not None else None,
            status=str(item["status"]),
            status_code=int(item["status_code"]) if item["status_code"] is not None else None,
            message=str(item["message"]),
            response_excerpt=str(item["response_excerpt"]) if item["response_excerpt"] is not None else None,
        )
        for item in result["attempts"]
    ]
    errors = [
        DiscoveryAttemptResponse(
            model=str(item["model"]) if item["model"] is not None else None,
            status=str(item["status"]),
            status_code=int(item["status_code"]) if item["status_code"] is not None else None,
            message=str(item["message"]),
            response_excerpt=str(item["response_excerpt"]) if item["response_excerpt"] is not None else None,
        )
        for item in result["errors"]
    ]
    return DiscoverySearchResponse(
        status=result["status"],
        query=str(result["query"]),
        risk_profile=result["risk_profile"],
        direction=result["direction"],
        asset_type=result["asset_type"],
        horizon=result["horizon"],
        provider=str(result["provider"]),
        primary_model=str(result["primary_model"]),
        validation_model=str(result["validation_model"]) if result["validation_model"] is not None else None,
        used_model=str(result["used_model"]) if result["used_model"] is not None else None,
        market_summary=str(result["market_summary"]) if result["market_summary"] is not None else None,
        local_candidates=local_candidates,
        ai_summary=str(result["ai_summary"]) if result["ai_summary"] is not None else None,
        candidates=ai_candidates,
        attempts=attempts,
        errors=errors,
        raw_response=str(result["raw_response"]) if result["raw_response"] is not None else None,
    )
