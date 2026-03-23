from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database import AsyncSessionLocal
from models import (
    AggregatedSentiment,
    AggregationSource,
    AggregationTimeframe,
    Asset,
    AssetType,
    PriceData,
    PriceTimeframe,
    SentimentRecord,
    SentimentSource,
    SignalType,
    TradingSignal,
)
from services.exceptions import ExternalAPIError
from services.perplexity_service import AIRequestAttempt, PerplexityService

RiskProfile = Literal["low", "balanced", "high"]
DiscoveryDirection = Literal["all", "buy", "sell"]
DiscoveryAssetType = Literal["all", "stock", "crypto"]
ScorecardHorizon = Literal["24h", "72h", "7d"]


class SignalLabService:
    """Discovery, signal scorecard and AI-supported idea search."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        ai_service: Optional[PerplexityService] = None,
    ) -> None:
        self._session_factory = session_factory
        self._ai = ai_service or PerplexityService()

    async def close(self) -> None:
        """Close managed resources."""
        await self._ai.close()

    async def get_scorecard(
        self,
        *,
        horizon: ScorecardHorizon = "72h",
        limit: int = 300,
        asset_type: DiscoveryAssetType = "all",
    ) -> Dict[str, Any]:
        """Return aggregated signal quality metrics for recent signals."""
        report = await self._build_scorecard_report(horizon=horizon, limit=limit, asset_type=asset_type)
        return {
            "horizon": report["horizon"],
            "total_signals": report["total_signals"],
            "evaluated_signals": report["evaluated_signals"],
            "buy_signals": report["buy_signals"],
            "sell_signals": report["sell_signals"],
            "hold_signals": report["hold_signals"],
            "hit_rate_pct": report["hit_rate_pct"],
            "avg_strategy_return_pct": report["avg_strategy_return_pct"],
            "avg_buy_return_pct": report["avg_buy_return_pct"],
            "avg_sell_return_pct": report["avg_sell_return_pct"],
            "positive_return_share_pct": report["positive_return_share_pct"],
            "top_symbols": report["top_symbols"],
            "weak_symbols": report["weak_symbols"],
            "recent": report["recent"],
        }

    async def get_discovery_candidates(
        self,
        *,
        risk_profile: RiskProfile = "balanced",
        direction: DiscoveryDirection = "buy",
        asset_type: DiscoveryAssetType = "all",
        horizon: ScorecardHorizon = "72h",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return locally ranked candidate ideas with risk and scorecard context."""
        scorecard_report = await self._build_scorecard_report(horizon=horizon, limit=300, asset_type=asset_type)
        symbol_stats = scorecard_report["symbol_stats"]
        async with self._session_factory() as session:
            active_rows = await self._load_active_signal_rows(session, direction=direction, asset_type=asset_type)
            if not active_rows:
                return []

            asset_ids = [asset.id for _, asset in active_rows]
            sentiment_map = await self._load_latest_sentiment_map(session, asset_ids)
            price_lookups = await self._load_price_lookups(session, asset_ids, since=datetime.now(timezone.utc) - timedelta(days=14))
            risk_map = self._build_risk_map(price_lookups)

        candidates: List[Dict[str, Any]] = []
        for signal, asset in active_rows:
            sentiment = sentiment_map.get(asset.id, {"score": None, "mentions": 0})
            risk = risk_map.get(
                asset.id,
                {
                    "volatility_pct": None,
                    "risk_bucket": "medium",
                    "risk_score": 50.0,
                    "latest_price": None,
                },
            )
            risk_fit_score = self._risk_fit_score(float(risk["risk_score"]), risk_profile)
            symbol_stat = symbol_stats.get(asset.symbol, {})
            aligned_sentiment_score = self._aligned_sentiment_score(
                signal_type=signal.signal_type,
                sentiment_score=sentiment.get("score"),
            )
            historical_hit_rate = self._to_optional_float(symbol_stat.get("hit_rate_pct"))
            historical_avg_return = self._to_optional_float(symbol_stat.get("avg_strategy_return_pct"))
            history_confidence = historical_hit_rate if historical_hit_rate is not None else 50.0
            discovery_score = (
                (0.45 * float(signal.strength))
                + (0.25 * float(risk_fit_score))
                + (0.15 * float(history_confidence))
                + (0.15 * float(aligned_sentiment_score))
            )
            candidates.append(
                {
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "asset_type": asset.asset_type.value,
                    "exchange": asset.exchange,
                    "signal_type": signal.signal_type,
                    "strength": float(signal.strength),
                    "composite_score": float(signal.composite_score),
                    "risk_bucket": risk["risk_bucket"],
                    "risk_score": float(risk["risk_score"]),
                    "risk_fit_score": float(risk_fit_score),
                    "volatility_pct": self._to_optional_float(risk["volatility_pct"]),
                    "sentiment_score": self._to_optional_float(sentiment.get("score")),
                    "mentions_1h": int(sentiment.get("mentions", 0) or 0),
                    "latest_price": self._to_optional_float(risk["latest_price"]),
                    "historical_hit_rate_pct": historical_hit_rate,
                    "historical_avg_return_pct": historical_avg_return,
                    "discovery_score": float(min(100.0, max(0.0, discovery_score))),
                    "reasoning": signal.reasoning,
                    "created_at": signal.created_at,
                }
            )

        candidates.sort(
            key=lambda item: (
                float(item["discovery_score"]),
                float(item["strength"]),
                float(item["risk_fit_score"]),
            ),
            reverse=True,
        )
        return candidates[: max(1, min(limit, 25))]

    async def run_discovery_search(
        self,
        *,
        query: str,
        risk_profile: RiskProfile = "balanced",
        direction: DiscoveryDirection = "buy",
        asset_type: DiscoveryAssetType = "all",
        horizon: ScorecardHorizon = "72h",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Run Sonar/GPT discovery on top of local signal, price and news context."""
        local_candidates = await self.get_discovery_candidates(
            risk_profile=risk_profile,
            direction=direction,
            asset_type=asset_type,
            horizon=horizon,
            limit=max(limit, 12),
        )
        async with self._session_factory() as session:
            market_summary = await self._latest_market_summary(session)
            recent_context = await self._recent_context_records(
                session,
                symbols=[item["symbol"] for item in local_candidates[:8]],
                limit=18,
            )

        prompt = self._build_discovery_prompt(
            query=query,
            risk_profile=risk_profile,
            direction=direction,
            asset_type=asset_type,
            horizon=horizon,
            limit=limit,
            market_summary=market_summary,
            local_candidates=local_candidates,
            recent_context=recent_context,
        )

        response: Dict[str, Any] = {
            "status": "success",
            "query": query.strip(),
            "risk_profile": risk_profile,
            "direction": direction,
            "asset_type": asset_type,
            "horizon": horizon,
            "provider": self._ai.provider,
            "primary_model": self._ai.primary_model,
            "validation_model": self._ai.validation_model,
            "used_model": None,
            "market_summary": market_summary,
            "local_candidates": local_candidates[:limit],
            "ai_summary": None,
            "candidates": [],
            "attempts": [],
            "errors": [],
            "raw_response": None,
        }
        try:
            ai_result = await self._ai.run_prompt_result(prompt, max_tokens=900)
            response["used_model"] = ai_result.model
            response["attempts"] = self._format_attempts(ai_result.attempts)
            response["raw_response"] = ai_result.content
            parsed = self._parse_discovery_response(ai_result.content)
            response["ai_summary"] = parsed["market_thesis"] or ai_result.content
            response["candidates"] = parsed["candidates"]
            if not parsed["candidates"]:
                response["status"] = "partial"
        except ExternalAPIError as exc:
            response["status"] = "error"
            response["errors"] = self._format_error(exc)
            response["attempts"] = self._format_error(exc)
        return response

    async def _build_scorecard_report(
        self,
        *,
        horizon: ScorecardHorizon,
        limit: int,
        asset_type: DiscoveryAssetType,
    ) -> Dict[str, Any]:
        safe_limit = max(25, min(limit, 500))
        async with self._session_factory() as session:
            signal_rows = await self._load_signal_rows(session, limit=safe_limit, asset_type=asset_type)
            evaluations = await self._evaluate_signals(session, signal_rows, horizon=horizon)
        return self._scorecard_from_evaluations(signal_rows=signal_rows, evaluations=evaluations, horizon=horizon)

    async def _load_signal_rows(
        self,
        session: AsyncSession,
        *,
        limit: int,
        asset_type: DiscoveryAssetType,
    ) -> List[Tuple[TradingSignal, Asset]]:
        query = (
            select(TradingSignal, Asset)
            .join(Asset, TradingSignal.asset_id == Asset.id)
            .order_by(TradingSignal.created_at.desc())
            .limit(limit)
        )
        if asset_type == "stock":
            query = query.where(Asset.asset_type == AssetType.STOCK)
        elif asset_type == "crypto":
            query = query.where(Asset.asset_type == AssetType.CRYPTO)
        return list((await session.execute(query)).all())

    async def _load_active_signal_rows(
        self,
        session: AsyncSession,
        *,
        direction: DiscoveryDirection,
        asset_type: DiscoveryAssetType,
    ) -> List[Tuple[TradingSignal, Asset]]:
        now = datetime.now(timezone.utc)
        query = (
            select(TradingSignal, Asset)
            .join(Asset, TradingSignal.asset_id == Asset.id)
            .where(
                TradingSignal.is_active.is_(True),
                or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
                Asset.is_active.is_(True),
            )
            .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
        )
        if direction == "buy":
            query = query.where(TradingSignal.signal_type == SignalType.BUY)
        elif direction == "sell":
            query = query.where(TradingSignal.signal_type == SignalType.SELL)
        if asset_type == "stock":
            query = query.where(Asset.asset_type == AssetType.STOCK)
        elif asset_type == "crypto":
            query = query.where(Asset.asset_type == AssetType.CRYPTO)
        return list((await session.execute(query)).all())

    async def _evaluate_signals(
        self,
        session: AsyncSession,
        signal_rows: Sequence[Tuple[TradingSignal, Asset]],
        *,
        horizon: ScorecardHorizon,
    ) -> List[Dict[str, Any]]:
        if not signal_rows:
            return []

        target_delta = self._horizon_delta(horizon)
        earliest_signal = min(item[0].created_at for item in signal_rows)
        asset_ids = list({asset.id for _, asset in signal_rows})
        price_lookups = await self._load_price_lookups(
            session,
            asset_ids,
            since=earliest_signal - timedelta(days=2),
        )

        evaluations: List[Dict[str, Any]] = []
        for signal, asset in signal_rows:
            entry_price = float(signal.price_at_signal)
            target_time = signal.created_at + target_delta
            future_price = self._lookup_future_price(price_lookups.get(asset.id), target_time)
            if future_price is None:
                continue
            raw_return_pct = self._percent_change(entry_price, float(future_price["price"]))
            strategy_return_pct = self._strategy_return(signal.signal_type, raw_return_pct)
            evaluations.append(
                {
                    "signal_id": signal.id,
                    "symbol": asset.symbol,
                    "signal_type": signal.signal_type,
                    "strength": float(signal.strength),
                    "created_at": signal.created_at,
                    "entry_price": entry_price,
                    "evaluation_price": float(future_price["price"]),
                    "raw_return_pct": float(raw_return_pct),
                    "strategy_return_pct": float(strategy_return_pct),
                    "success": self._is_success(signal.signal_type, raw_return_pct),
                    "horizon": horizon,
                    "reasoning": signal.reasoning,
                }
            )
        return evaluations

    async def _load_price_lookups(
        self,
        session: AsyncSession,
        asset_ids: Sequence[int],
        *,
        since: datetime,
    ) -> Dict[int, Dict[str, Any]]:
        if not asset_ids:
            return {}
        query = (
            select(PriceData)
            .where(
                PriceData.asset_id.in_(asset_ids),
                PriceData.timestamp >= since,
                PriceData.timeframe.in_([PriceTimeframe.H1, PriceTimeframe.D1]),
            )
            .order_by(PriceData.asset_id.asc(), PriceData.timestamp.asc())
        )
        rows = list((await session.execute(query)).scalars().all())
        lookups: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            bucket = lookups.setdefault(
                row.asset_id,
                {
                    "timestamps": [],
                    "prices": [],
                    "timeframes": [],
                },
            )
            bucket["timestamps"].append(row.timestamp)
            bucket["prices"].append(float(row.close))
            bucket["timeframes"].append(row.timeframe.value)
        return lookups

    async def _load_latest_sentiment_map(
        self,
        session: AsyncSession,
        asset_ids: Sequence[int],
    ) -> Dict[int, Dict[str, Any]]:
        if not asset_ids:
            return {}
        query = (
            select(AggregatedSentiment)
            .where(
                AggregatedSentiment.asset_id.in_(asset_ids),
                AggregatedSentiment.timeframe == AggregationTimeframe.H1,
                AggregatedSentiment.source == AggregationSource.ALL,
            )
            .order_by(AggregatedSentiment.asset_id.asc(), AggregatedSentiment.period_end.desc())
        )
        rows = list((await session.execute(query)).scalars().all())
        by_asset: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            if row.asset_id in by_asset:
                continue
            by_asset[row.asset_id] = {
                "score": float(row.weighted_score) * 100.0,
                "mentions": int(row.total_mentions),
                "updated_at": row.period_end,
            }
        return by_asset

    async def _latest_market_summary(self, session: AsyncSession) -> Optional[str]:
        query = (
            select(SentimentRecord)
            .where(
                SentimentRecord.source == SentimentSource.PERPLEXITY,
                SentimentRecord.asset_id.is_(None),
            )
            .order_by(SentimentRecord.created_at.desc())
            .limit(1)
        )
        record = (await session.execute(query)).scalar_one_or_none()
        if record is None:
            return None
        return record.text_snippet

    async def _recent_context_records(
        self,
        session: AsyncSession,
        *,
        symbols: Sequence[str],
        limit: int,
    ) -> List[str]:
        if not symbols:
            return []
        asset_query = select(Asset.id, Asset.symbol).where(Asset.symbol.in_(list(symbols)))
        asset_rows = (await session.execute(asset_query)).all()
        if not asset_rows:
            return []
        symbol_by_id = {asset_id: symbol for asset_id, symbol in asset_rows}
        asset_ids = list(symbol_by_id.keys())
        query = (
            select(SentimentRecord)
            .where(
                SentimentRecord.asset_id.in_(asset_ids),
                SentimentRecord.source.in_(
                    [
                        SentimentSource.NEWS,
                        SentimentSource.REDDIT,
                        SentimentSource.STOCKTWITS,
                    ]
                ),
            )
            .order_by(SentimentRecord.created_at.desc())
            .limit(max(6, min(limit, 30)))
        )
        rows = list((await session.execute(query)).scalars().all())
        snippets: List[str] = []
        for row in rows:
            symbol = symbol_by_id.get(row.asset_id or -1)
            if symbol is None:
                continue
            snippets.append(
                "{0} | {1} | {2}".format(
                    symbol,
                    row.source.value,
                    self._trim_text(row.text_snippet, limit=180),
                )
            )
        return snippets

    def _scorecard_from_evaluations(
        self,
        *,
        signal_rows: Sequence[Tuple[TradingSignal, Asset]],
        evaluations: Sequence[Dict[str, Any]],
        horizon: ScorecardHorizon,
    ) -> Dict[str, Any]:
        total_signals = len(signal_rows)
        evaluated_signals = len(evaluations)
        buy_signals = sum(1 for signal, _ in signal_rows if signal.signal_type == SignalType.BUY)
        sell_signals = sum(1 for signal, _ in signal_rows if signal.signal_type == SignalType.SELL)
        hold_signals = sum(1 for signal, _ in signal_rows if signal.signal_type == SignalType.HOLD)
        success_count = sum(1 for row in evaluations if row["success"])
        strategy_returns = [float(row["strategy_return_pct"]) for row in evaluations]
        positive_return_share = (
            (sum(1 for value in strategy_returns if value > 0.0) / len(strategy_returns)) * 100.0
            if strategy_returns
            else 0.0
        )
        buy_returns = [float(row["strategy_return_pct"]) for row in evaluations if row["signal_type"] == SignalType.BUY]
        sell_returns = [float(row["strategy_return_pct"]) for row in evaluations if row["signal_type"] == SignalType.SELL]

        symbol_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in evaluations:
            symbol_groups[str(row["symbol"])].append(row)
        symbol_stats: Dict[str, Dict[str, Any]] = {}
        for symbol, rows in symbol_groups.items():
            hits = sum(1 for row in rows if row["success"])
            returns = [float(row["strategy_return_pct"]) for row in rows]
            symbol_stats[symbol] = {
                "symbol": symbol,
                "evaluated_signals": len(rows),
                "hit_rate_pct": (hits / len(rows)) * 100.0 if rows else 0.0,
                "avg_strategy_return_pct": sum(returns) / len(returns) if returns else 0.0,
            }
        ranked_symbols = sorted(
            symbol_stats.values(),
            key=lambda item: (float(item["avg_strategy_return_pct"]), float(item["hit_rate_pct"])),
            reverse=True,
        )
        weak_symbols = sorted(
            symbol_stats.values(),
            key=lambda item: (float(item["avg_strategy_return_pct"]), float(item["hit_rate_pct"])),
        )
        recent_rows = sorted(
            evaluations,
            key=lambda item: (item["created_at"], item["signal_id"]),
            reverse=True,
        )[:20]
        return {
            "horizon": horizon,
            "total_signals": total_signals,
            "evaluated_signals": evaluated_signals,
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "hold_signals": hold_signals,
            "hit_rate_pct": ((success_count / evaluated_signals) * 100.0) if evaluated_signals else 0.0,
            "avg_strategy_return_pct": (sum(strategy_returns) / len(strategy_returns)) if strategy_returns else 0.0,
            "avg_buy_return_pct": (sum(buy_returns) / len(buy_returns)) if buy_returns else None,
            "avg_sell_return_pct": (sum(sell_returns) / len(sell_returns)) if sell_returns else None,
            "positive_return_share_pct": positive_return_share,
            "top_symbols": ranked_symbols[:5],
            "weak_symbols": weak_symbols[:5],
            "recent": recent_rows,
            "symbol_stats": symbol_stats,
        }

    def _build_risk_map(self, price_lookups: Mapping[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        volatility_by_asset: Dict[int, Optional[float]] = {}
        for asset_id, lookup in price_lookups.items():
            volatility_by_asset[asset_id] = self._volatility_from_lookup(lookup)

        values = [value for value in volatility_by_asset.values() if value is not None]
        if not values:
            return {}
        sorted_values = sorted(values)
        low_cut = self._percentile(sorted_values, 0.33)
        high_cut = self._percentile(sorted_values, 0.66)
        risk_map: Dict[int, Dict[str, Any]] = {}
        for asset_id, lookup in price_lookups.items():
            volatility = volatility_by_asset.get(asset_id)
            if volatility is None:
                risk_score = 50.0
                risk_bucket = "medium"
            else:
                risk_score = self._percentile_rank(sorted_values, volatility)
                if volatility <= low_cut:
                    risk_bucket = "low"
                elif volatility >= high_cut:
                    risk_bucket = "high"
                else:
                    risk_bucket = "medium"
            latest_price = lookup["prices"][-1] if lookup.get("prices") else None
            risk_map[asset_id] = {
                "volatility_pct": volatility,
                "risk_bucket": risk_bucket,
                "risk_score": risk_score,
                "latest_price": latest_price,
            }
        return risk_map

    def _lookup_future_price(
        self,
        lookup: Optional[Mapping[str, Any]],
        target_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        if lookup is None:
            return None
        timestamps = lookup.get("timestamps") or []
        prices = lookup.get("prices") or []
        if not timestamps or not prices:
            return None
        index = bisect_left(timestamps, target_time)
        if index >= len(prices):
            return None
        return {
            "timestamp": timestamps[index],
            "price": prices[index],
        }

    def _build_discovery_prompt(
        self,
        *,
        query: str,
        risk_profile: RiskProfile,
        direction: DiscoveryDirection,
        asset_type: DiscoveryAssetType,
        horizon: ScorecardHorizon,
        limit: int,
        market_summary: Optional[str],
        local_candidates: Sequence[Mapping[str, Any]],
        recent_context: Sequence[str],
    ) -> str:
        candidate_lines = []
        for item in local_candidates[:12]:
            candidate_lines.append(
                "- {0} | signal={1} | strength={2:.1f} | risk={3} | risk_fit={4:.1f} | vol={5} | sentiment={6} | hit_rate={7} | avg_return={8}".format(
                    item["symbol"],
                    item["signal_type"],
                    float(item["strength"]),
                    item["risk_bucket"],
                    float(item["risk_fit_score"]),
                    self._format_optional_number(item.get("volatility_pct"), suffix="%"),
                    self._format_optional_number(item.get("sentiment_score")),
                    self._format_optional_number(item.get("historical_hit_rate_pct"), suffix="%"),
                    self._format_optional_number(item.get("historical_avg_return_pct"), suffix="%"),
                )
            )
        context_lines = "\n".join("- {0}".format(item) for item in recent_context[:18]) or "- Keine frischen News-Snippets vorhanden."
        market_context = market_summary or "Keine globale Market Summary vorhanden."
        return (
            "Du bist ein Discovery-Analyst fuer Aktien und Krypto.\n"
            "Nutze die lokale Scorecard, die Risiko-Einteilung und die News-/Social-Snippets, um Discovery-Kandidaten zu finden.\n"
            "Die Antwort muss JSON ONLY sein und dieses Schema haben:\n"
            '{'
            '"market_thesis":"kurze Zusammenfassung",'
            '"candidates":[{"symbol":"AAPL","action":"buy|watch|avoid|sell","thesis":"warum jetzt",'
            '"risk_note":"welches Risiko",'
            '"confidence":0.0}]}'
            "\n"
            "Suche: {0}\n"
            "Risikoprofil: {1}\n"
            "Richtung: {2}\n"
            "Asset-Typ: {3}\n"
            "Bewertungshorizont: {4}\n"
            "Gewuenschte Anzahl: {5}\n\n"
            "Lokale Kandidaten:\n{6}\n\n"
            "Market Summary:\n{7}\n\n"
            "Aktuelle News-/Social-Snippets:\n{8}\n"
            "Bevorzuge Kandidaten, deren lokale Scorecard und Signalqualitaet bereits nachvollziehbar sind."
        ).format(
            query.strip() or "Finde die besten Discovery-Kandidaten.",
            risk_profile,
            direction,
            asset_type,
            horizon,
            limit,
            "\n".join(candidate_lines) or "- Keine lokalen Kandidaten vorhanden.",
            market_context,
            context_lines,
        )

    def _parse_discovery_response(self, content: str) -> Dict[str, Any]:
        extracted = self._extract_json_object(content)
        if extracted is None:
            return {"market_thesis": content.strip(), "candidates": []}
        try:
            payload = json.loads(extracted)
        except json.JSONDecodeError:
            return {"market_thesis": content.strip(), "candidates": []}
        candidates = []
        raw_candidates = payload.get("candidates")
        if isinstance(raw_candidates, list):
            for item in raw_candidates[:20]:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol", "")).upper().strip()
                if not symbol:
                    continue
                confidence = item.get("confidence")
                candidates.append(
                    {
                        "symbol": symbol,
                        "action": str(item.get("action", "watch")).strip() or "watch",
                        "thesis": str(item.get("thesis", "")).strip(),
                        "risk_note": str(item.get("risk_note", "")).strip(),
                        "confidence": self._to_optional_float(confidence),
                    }
                )
        return {
            "market_thesis": str(payload.get("market_thesis", "")).strip(),
            "candidates": candidates,
        }

    def _format_attempts(self, attempts: Iterable[AIRequestAttempt]) -> List[Dict[str, Any]]:
        return [
            {
                "model": item.model,
                "status": item.status,
                "status_code": item.status_code,
                "message": item.error or ("Erfolgreich" if item.status == "success" else "Unbekannter Fehler"),
                "response_excerpt": item.response_excerpt,
            }
            for item in attempts
        ]

    def _format_error(self, error: ExternalAPIError) -> List[Dict[str, Any]]:
        if error.attempts:
            return self._format_attempts(item for item in error.attempts if isinstance(item, AIRequestAttempt))
        return [
            {
                "model": error.model,
                "status": "error",
                "status_code": error.status_code,
                "message": str(error),
                "response_excerpt": error.response_body,
            }
        ]

    def _volatility_from_lookup(self, lookup: Mapping[str, Any]) -> Optional[float]:
        prices = lookup.get("prices") or []
        timeframes = lookup.get("timeframes") or []
        h1_prices = [float(price) for price, timeframe in zip(prices, timeframes) if timeframe == PriceTimeframe.H1.value]
        d1_prices = [float(price) for price, timeframe in zip(prices, timeframes) if timeframe == PriceTimeframe.D1.value]
        series = h1_prices if len(h1_prices) >= 24 else d1_prices
        if len(series) < 8:
            return None
        returns: List[float] = []
        for previous_float, current_float in zip(series, series[1:]):
            if previous_float <= 0:
                continue
            returns.append(((current_float - previous_float) / previous_float) * 100.0)
        if len(returns) < 12:
            return None
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / len(returns)
        return variance ** 0.5

    def _percentile(self, values: Sequence[float], point: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        raw_index = point * (len(values) - 1)
        lower = int(raw_index)
        upper = min(len(values) - 1, lower + 1)
        weight = raw_index - lower
        return float(values[lower] + ((values[upper] - values[lower]) * weight))

    def _percentile_rank(self, sorted_values: Sequence[float], value: float) -> float:
        if not sorted_values:
            return 50.0
        index = bisect_left(list(sorted_values), value)
        return max(0.0, min(100.0, (index / max(1, len(sorted_values) - 1)) * 100.0))

    def _risk_fit_score(self, risk_score: float, risk_profile: RiskProfile) -> float:
        if risk_profile == "low":
            return max(0.0, min(100.0, 100.0 - risk_score))
        if risk_profile == "high":
            return max(0.0, min(100.0, risk_score))
        return max(0.0, min(100.0, 100.0 - (abs(risk_score - 50.0) * 2.0)))

    def _aligned_sentiment_score(self, *, signal_type: SignalType, sentiment_score: Optional[float]) -> float:
        if sentiment_score is None:
            return 50.0
        if signal_type == SignalType.BUY:
            aligned = sentiment_score
        elif signal_type == SignalType.SELL:
            aligned = -sentiment_score
        else:
            aligned = -abs(sentiment_score) / 2.0
        return max(0.0, min(100.0, (aligned + 100.0) / 2.0))

    def _strategy_return(self, signal_type: SignalType, raw_return_pct: float) -> float:
        if signal_type == SignalType.BUY:
            return raw_return_pct
        if signal_type == SignalType.SELL:
            return -raw_return_pct
        return -abs(raw_return_pct)

    def _is_success(self, signal_type: SignalType, raw_return_pct: float) -> bool:
        if signal_type == SignalType.BUY:
            return raw_return_pct > 0.0
        if signal_type == SignalType.SELL:
            return raw_return_pct < 0.0
        return abs(raw_return_pct) <= 1.5

    def _horizon_delta(self, horizon: ScorecardHorizon) -> timedelta:
        if horizon == "24h":
            return timedelta(hours=24)
        if horizon == "72h":
            return timedelta(hours=72)
        return timedelta(days=7)

    def _percent_change(self, previous: float, current: float) -> float:
        if previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100.0

    def _extract_json_object(self, content: str) -> Optional[str]:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return content[start : end + 1]

    def _format_optional_number(self, value: Any, *, suffix: str = "") -> str:
        numeric = self._to_optional_float(value)
        if numeric is None:
            return "n/a"
        return "{0:.2f}{1}".format(numeric, suffix)

    def _to_optional_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _trim_text(self, value: str, *, limit: int = 200) -> str:
        normalized = value.strip()
        if len(normalized) <= limit:
            return normalized
        return "{0}...".format(normalized[:limit])
