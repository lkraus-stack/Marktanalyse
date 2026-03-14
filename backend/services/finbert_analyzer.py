from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Sequence

from config import get_settings
from services.exceptions import ExternalAPIError

logger = logging.getLogger("market_intelligence.services.finbert_analyzer")


class FinBERTAnalyzer:
    """Lazy-loaded FinBERT analyzer with CPU-friendly defaults."""

    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = settings.finbert_enabled
        self._pipeline = None
        self._available = settings.finbert_enabled
        self._load_attempted = False
        self._load_lock = asyncio.Lock()

    def is_available(self) -> bool:
        """Return current FinBERT availability state."""
        return self._available and self._enabled

    async def analyze(self, text: str) -> Dict[str, Any]:
        """Analyze one text with FinBERT."""
        results = await self.analyze_batch([text], batch_size=1)
        if not results:
            raise ExternalAPIError("FinBERT did not return an output.")
        return results[0]

    async def analyze_batch(self, texts: Sequence[str], batch_size: int = 16) -> List[Dict[str, Any]]:
        """Analyze texts in batches and normalize the result payload."""
        if not texts:
            return []
        await self._ensure_model_loaded()
        if not self.is_available():
            raise ExternalAPIError("FinBERT not available.")
        chunks = self._chunk_texts(list(texts), batch_size=max(1, batch_size))
        normalized: List[Dict[str, Any]] = []
        for chunk in chunks:
            raw_chunk = await asyncio.to_thread(self._pipeline, chunk, truncation=True, max_length=512)
            normalized.extend([self._normalize_output(item) for item in raw_chunk])
        return normalized

    async def _ensure_model_loaded(self) -> None:
        if not self._enabled:
            self._available = False
            return
        if self._load_attempted:
            return
        async with self._load_lock:
            if self._load_attempted:
                return
            await self._load_pipeline()

    async def _load_pipeline(self) -> None:
        try:
            self._pipeline = await asyncio.to_thread(self._build_pipeline)
            self._available = True
            logger.info("FinBERT model loaded.", extra={"event": "finbert_loaded"})
        except Exception:
            self._available = False
            logger.exception("FinBERT unavailable; falling back to FinVADER.", extra={"event": "finbert_unavailable"})
        finally:
            self._load_attempted = True

    def _build_pipeline(self):
        from transformers import pipeline

        return pipeline(
            task="text-classification",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1,
        )

    def _chunk_texts(self, texts: List[str], batch_size: int) -> List[List[str]]:
        return [texts[idx : idx + batch_size] for idx in range(0, len(texts), batch_size)]

    def _normalize_output(self, item: Dict[str, Any]) -> Dict[str, Any]:
        raw_label = str(item.get("label", "neutral")).lower()
        confidence = float(item.get("score", 0.0))
        if "pos" in raw_label:
            label = "positive"
            score = confidence
        elif "neg" in raw_label:
            label = "negative"
            score = -confidence
        else:
            label = "neutral"
            score = 0.0
        return {"score": float(max(-1.0, min(1.0, score))), "label": label, "confidence": confidence, "model": "finbert"}
