from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands


@dataclass(frozen=True)
class TechnicalThresholds:
    """Threshold definitions for technical signal scoring."""

    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    bollinger_near_ratio: float = 0.15
    volume_high_ratio: float = 1.2


class TechnicalAnalyzer:
    """Computes technical indicators and a normalized score."""

    def __init__(self, thresholds: TechnicalThresholds | None = None) -> None:
        self._thresholds = thresholds or TechnicalThresholds()

    def calculate_indicators(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate RSI, MACD, Bollinger, SMA crosses and volume context."""
        frame = self._prepare_frame(price_data)
        if frame.empty:
            return self._empty_indicator_payload()

        close = frame["close"]
        volume = frame["volume"]

        result: Dict[str, Any] = {
            "data_points": int(len(frame)),
            "latest_close": float(close.iloc[-1]),
        }

        rsi_series = RSIIndicator(close=close, window=14).rsi()
        latest_rsi = self._safe_last(rsi_series)
        if latest_rsi is None:
            result["rsi"] = {"value": None, "zone": "unknown"}
        else:
            if latest_rsi < self._thresholds.rsi_oversold:
                rsi_zone = "oversold"
            elif latest_rsi > self._thresholds.rsi_overbought:
                rsi_zone = "overbought"
            else:
                rsi_zone = "neutral"
            result["rsi"] = {"value": latest_rsi, "zone": rsi_zone}

        macd = MACD(close=close)
        macd_line = macd.macd()
        macd_signal = macd.macd_signal()
        macd_state = self._detect_macd_cross(macd_line, macd_signal)
        result["macd"] = {
            "state": macd_state,
            "macd": self._safe_last(macd_line),
            "signal": self._safe_last(macd_signal),
        }

        bollinger = BollingerBands(close=close, window=20, window_dev=2)
        upper = self._safe_last(bollinger.bollinger_hband())
        lower = self._safe_last(bollinger.bollinger_lband())
        bb_position = self._detect_bollinger_position(
            price=float(close.iloc[-1]),
            lower=lower,
            upper=upper,
        )
        result["bollinger"] = {
            "position": bb_position,
            "upper": upper,
            "lower": lower,
        }

        sma_20 = SMAIndicator(close=close, window=20).sma_indicator()
        sma_50 = SMAIndicator(close=close, window=50).sma_indicator()
        cross_state = self._detect_sma_cross(sma_20, sma_50)
        result["sma"] = {
            "sma20": self._safe_last(sma_20),
            "sma50": self._safe_last(sma_50),
            "cross": cross_state,
        }

        volume_avg_20 = float(volume.tail(20).mean()) if len(volume) >= 20 else None
        latest_volume = float(volume.iloc[-1]) if len(volume) > 0 else 0.0
        previous_close = float(close.iloc[-2]) if len(close) >= 2 else float(close.iloc[-1])
        latest_close = float(close.iloc[-1])
        price_direction = "up" if latest_close >= previous_close else "down"
        if volume_avg_20 and volume_avg_20 > 0:
            volume_ratio = latest_volume / volume_avg_20
            is_high_volume = volume_ratio >= self._thresholds.volume_high_ratio
        else:
            volume_ratio = None
            is_high_volume = False

        result["volume"] = {
            "latest": latest_volume,
            "avg_20": volume_avg_20,
            "ratio": volume_ratio,
            "is_high": is_high_volume,
            "price_direction": price_direction,
        }
        return result

    def get_technical_score(self, indicators: Dict[str, Any]) -> float:
        """Calculate technical composite score in range [-100, +100]."""
        score = 0.0

        rsi = indicators.get("rsi", {})
        rsi_zone = rsi.get("zone")
        if rsi_zone == "oversold":
            score += 20.0
        elif rsi_zone == "overbought":
            score -= 20.0

        macd = indicators.get("macd", {})
        macd_state = macd.get("state")
        if macd_state == "bullish_cross":
            score += 25.0
        elif macd_state == "bearish_cross":
            score -= 25.0

        bollinger = indicators.get("bollinger", {})
        bollinger_pos = bollinger.get("position")
        if bollinger_pos == "near_lower":
            score += 15.0
        elif bollinger_pos == "near_upper":
            score -= 15.0

        sma = indicators.get("sma", {})
        sma_cross = sma.get("cross")
        if sma_cross == "golden_cross":
            score += 20.0
        elif sma_cross == "death_cross":
            score -= 20.0

        volume = indicators.get("volume", {})
        if volume.get("is_high"):
            if volume.get("price_direction") == "up":
                score += 10.0
            elif volume.get("price_direction") == "down":
                score -= 10.0

        return max(-100.0, min(100.0, score))

    def _prepare_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        required_cols = ["open", "high", "low", "close", "volume"]
        if frame.empty:
            return pd.DataFrame(columns=required_cols)
        copy = frame.copy()
        for col in required_cols:
            if col not in copy.columns:
                copy[col] = 0.0
            copy[col] = pd.to_numeric(copy[col], errors="coerce")
        copy = copy.dropna(subset=["close"]).sort_index()
        copy = copy.ffill().fillna(0.0)
        return copy

    def _empty_indicator_payload(self) -> Dict[str, Any]:
        return {
            "data_points": 0,
            "latest_close": None,
            "rsi": {"value": None, "zone": "unknown"},
            "macd": {"state": "none", "macd": None, "signal": None},
            "bollinger": {"position": "unknown", "upper": None, "lower": None},
            "sma": {"sma20": None, "sma50": None, "cross": "none"},
            "volume": {"latest": 0.0, "avg_20": None, "ratio": None, "is_high": False, "price_direction": "flat"},
        }

    def _safe_last(self, series: pd.Series) -> float | None:
        filtered = series.dropna()
        if filtered.empty:
            return None
        return float(filtered.iloc[-1])

    def _detect_macd_cross(self, macd_line: pd.Series, signal_line: pd.Series) -> str:
        aligned = pd.DataFrame({"macd": macd_line, "signal": signal_line}).dropna()
        if len(aligned) < 2:
            return "none"
        prev_diff = float(aligned.iloc[-2]["macd"] - aligned.iloc[-2]["signal"])
        curr_diff = float(aligned.iloc[-1]["macd"] - aligned.iloc[-1]["signal"])
        if prev_diff <= 0 and curr_diff > 0:
            return "bullish_cross"
        if prev_diff >= 0 and curr_diff < 0:
            return "bearish_cross"
        return "none"

    def _detect_bollinger_position(self, price: float, lower: float | None, upper: float | None) -> str:
        if lower is None or upper is None or upper <= lower:
            return "unknown"
        width = upper - lower
        if width <= 0:
            return "unknown"
        near = width * self._thresholds.bollinger_near_ratio
        if price <= (lower + near):
            return "near_lower"
        if price >= (upper - near):
            return "near_upper"
        return "middle"

    def _detect_sma_cross(self, sma20: pd.Series, sma50: pd.Series) -> str:
        aligned = pd.DataFrame({"sma20": sma20, "sma50": sma50}).dropna()
        if len(aligned) < 2:
            return "none"
        prev_diff = float(aligned.iloc[-2]["sma20"] - aligned.iloc[-2]["sma50"])
        curr_diff = float(aligned.iloc[-1]["sma20"] - aligned.iloc[-1]["sma50"])
        if prev_diff <= 0 and curr_diff > 0:
            return "golden_cross"
        if prev_diff >= 0 and curr_diff < 0:
            return "death_cross"
        return "none"
