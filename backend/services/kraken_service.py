from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from config import get_settings
from services.exceptions import ExternalAPIError, InsufficientFundsError, InvalidSymbolError, MarketClosedError

logger = logging.getLogger("market_intelligence.services.kraken")


class KrakenService:
    """Async Kraken REST client with HMAC-SHA512 authentication."""

    _PUBLIC_BASE = "/0/public"
    _PRIVATE_BASE = "/0/private"

    SYMBOL_TO_PAIR = {
        "BTC": "XXBTZEUR",
        "ETH": "XETHZEUR",
        "SOL": "SOLEUR",
    }

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.kraken_api_key
        self._secret = settings.kraken_secret_key
        self._base_url = settings.kraken_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=20.0)
        self._last_nonce = int(time.time() * 1000)

    def is_configured(self) -> bool:
        """Return True if Kraken API credentials are available."""
        return bool(self._api_key and self._secret)

    def map_symbol_to_pair(self, symbol: str) -> str:
        """Map internal symbol to Kraken pair."""
        key = symbol.upper().strip()
        pair = self.SYMBOL_TO_PAIR.get(key)
        if pair is None:
            raise InvalidSymbolError("Kein Kraken-Pair-Mapping fuer Symbol '{0}'.".format(symbol))
        return pair

    async def get_balance(self) -> Dict[str, Any]:
        """Return account balances from Kraken."""
        return await self._private_request("Balance")

    async def get_open_orders(self) -> Dict[str, Any]:
        """Return currently open Kraken orders."""
        return await self._private_request("OpenOrders")

    async def submit_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        volume: float,
    ) -> Dict[str, Any]:
        """Submit one order to Kraken."""
        payload = {
            "pair": pair,
            "type": side,
            "ordertype": order_type,
            "volume": str(volume),
        }
        return await self._private_request("AddOrder", payload)

    async def get_trade_history(self) -> Dict[str, Any]:
        """Return historical trades from Kraken."""
        return await self._private_request("TradesHistory")

    async def cancel_order(self, txid: str) -> Dict[str, Any]:
        """Cancel an order by txid."""
        return await self._private_request("CancelOrder", {"txid": txid})

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._client.aclose()

    async def _private_request(
        self,
        method: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise ExternalAPIError("Kraken credentials are not configured.")

        nonce = self._next_nonce()
        body: Dict[str, Any] = dict(payload or {})
        body["nonce"] = str(nonce)
        path = "{0}/{1}".format(self._PRIVATE_BASE, method)
        encoded = urlencode(body)
        signature = self._build_signature(path=path, data=encoded, nonce=str(nonce))
        headers = {
            "API-Key": str(self._api_key),
            "API-Sign": signature,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        url = "{0}{1}".format(self._base_url, path)
        try:
            response = await self._client.post(url, content=encoded, headers=headers)
        except httpx.HTTPError as exc:
            raise ExternalAPIError("Kraken request failed: {0}".format(str(exc))) from exc

        try:
            payload_obj = response.json()
        except ValueError as exc:
            raise ExternalAPIError("Kraken response was not valid JSON.") from exc
        if not isinstance(payload_obj, dict):
            raise ExternalAPIError("Unexpected Kraken response format.")

        errors = payload_obj.get("error", [])
        if isinstance(errors, list) and errors:
            joined = ", ".join(str(item) for item in errors)
            self._raise_mapped_error(joined)

        result = payload_obj.get("result", {})
        if isinstance(result, dict):
            return result
        raise ExternalAPIError("Unexpected Kraken result payload.")

    def _build_signature(self, path: str, data: str, nonce: str) -> str:
        if not self._secret:
            raise ExternalAPIError("Kraken secret missing.")
        postdata = "{0}{1}".format(nonce, data)
        sha256_hash = hashlib.sha256(postdata.encode("utf-8")).digest()
        message = path.encode("utf-8") + sha256_hash
        try:
            secret_decoded = base64.b64decode(self._secret)
        except Exception as exc:
            raise ExternalAPIError("Kraken secret is not valid base64.") from exc
        mac = hmac.new(secret_decoded, message, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _next_nonce(self) -> int:
        now_ms = int(time.time() * 1000)
        if now_ms <= self._last_nonce:
            self._last_nonce += 1
        else:
            self._last_nonce = now_ms
        return self._last_nonce

    def _raise_mapped_error(self, message: str) -> None:
        normalized = message.lower()
        if "insufficient" in normalized:
            raise InsufficientFundsError(message)
        if "market" in normalized and ("closed" in normalized or "halted" in normalized):
            raise MarketClosedError(message)
        if "invalid" in normalized and "pair" in normalized:
            raise InvalidSymbolError(message)
        raise ExternalAPIError("Kraken API error: {0}".format(message))
