from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from services.exceptions import ExternalAPIError

logger = logging.getLogger("market_intelligence.services.finvader_analyzer")


class FinVADERAnalyzer:
    """Fast rule-based sentiment analyzer for financial text."""

    def __init__(self) -> None:
        self._finvader_callable = None

    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyze one text and return normalized sentiment payload."""
        score = self._calculate_compound_score(text)
        label = self._map_label(score)
        confidence = self._calculate_confidence(score, label)
        return {"score": score, "label": label, "confidence": confidence, "model": "finvader"}

    def analyze_batch(self, texts: Sequence[str]) -> List[Dict[str, Any]]:
        """Analyze multiple texts sequentially."""
        return [self.analyze(text) for text in texts]

    def _calculate_compound_score(self, text: str) -> float:
        callable_ref = self._load_finvader_callable()
        raw_score = callable_ref(text=text or "", indicator="compound", use_sentibignomics=True, use_henry=True)
        return max(-1.0, min(1.0, float(raw_score)))

    def _load_finvader_callable(self):
        if self._finvader_callable is not None:
            return self._finvader_callable
        try:
            from finvader import finvader as finvader_callable
        except Exception as exc:
            logger.exception("FinVADER import failed.", extra={"event": "finvader_import_failed"})
            raise ExternalAPIError("FinVADER dependency not available.") from exc
        self._finvader_callable = finvader_callable
        return self._finvader_callable

    def _map_label(self, score: float) -> str:
        if score > 0.05:
            return "positive"
        if score < -0.05:
            return "negative"
        return "neutral"

    def _calculate_confidence(self, score: float, label: str) -> float:
        absolute = abs(score)
        if label == "neutral":
            return round(max(0.0, min(1.0, 1.0 - absolute)), 4)
        return round(max(0.0, min(1.0, absolute)), 4)
