from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import get_settings
from services.exceptions import ExternalAPIError, InsufficientFundsError, InvalidSymbolError, MarketClosedError

logger = logging.getLogger("market_intelligence.services.alpaca")


class AlpacaService:
    """Thin async client for Alpaca paper trading API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key
        self._paper_base_url = settings.alpaca_paper_base_url.rstrip("/")
        self._live_base_url = settings.alpaca_live_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=20.0)

    def is_configured(self) -> bool:
        """Return True when Alpaca credentials are present."""
        return bool(self._api_key and self._secret_key)

    async def get_account(self, live: bool = False) -> Dict[str, Any]:
        """Fetch account details."""
        payload = await self._request("GET", "/v2/account", live=live)
        if not isinstance(payload, dict):
            raise ExternalAPIError("Unexpected Alpaca account response format.")
        return payload

    async def get_positions(self, live: bool = False) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        payload = await self._request("GET", "/v2/positions", live=live)
        if not isinstance(payload, list):
            raise ExternalAPIError("Unexpected Alpaca positions response format.")
        return [item for item in payload if isinstance(item, dict)]

    async def get_portfolio_history(
        self,
        period: str = "1M",
        timeframe: str = "1D",
        live: bool = False,
    ) -> Dict[str, Any]:
        """Fetch equity history for performance charting."""
        payload = await self._request(
            "GET",
            "/v2/account/portfolio/history",
            params={"period": period, "timeframe": timeframe},
            live=live,
        )
        if not isinstance(payload, dict):
            raise ExternalAPIError("Unexpected Alpaca portfolio history response format.")
        return payload

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        client_order_id: Optional[str] = None,
        live: bool = False,
    ) -> Dict[str, Any]:
        """Submit one order to Alpaca."""
        body: Dict[str, Any] = {
            "symbol": symbol.upper().strip(),
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        payload = await self._request("POST", "/v2/orders", json=body, live=live)
        if not isinstance(payload, dict):
            raise ExternalAPIError("Unexpected Alpaca order response format.")
        return payload

    async def get_order(self, order_id: str, live: bool = False) -> Dict[str, Any]:
        """Fetch single order details."""
        payload = await self._request("GET", "/v2/orders/{0}".format(order_id), live=live)
        if not isinstance(payload, dict):
            raise ExternalAPIError("Unexpected Alpaca order response format.")
        return payload

    async def get_order_by_client_order_id(self, client_order_id: str, live: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch order by client-provided id for idempotency handling."""
        try:
            payload = await self._request(
                "GET",
                "/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
                live=live,
            )
        except ExternalAPIError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                return None
            raise
        if isinstance(payload, dict):
            return payload
        return None

    async def cancel_order(self, order_id: str, live: bool = False) -> bool:
        """Cancel one existing order."""
        await self._request("DELETE", "/v2/orders/{0}".format(order_id), live=live)
        return True

    async def close(self) -> None:
        """Release network resources."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        live: bool = False,
    ) -> Any:
        if not self.is_configured():
            raise ExternalAPIError("Alpaca credentials are not configured.")

        headers = {
            "APCA-API-KEY-ID": str(self._api_key),
            "APCA-API-SECRET-KEY": str(self._secret_key),
        }
        base_url = self._live_base_url if live else self._paper_base_url
        url = "{0}{1}".format(base_url, path)
        try:
            response = await self._client.request(method, url, headers=headers, params=params, json=json)
        except httpx.HTTPError as exc:
            raise ExternalAPIError("Alpaca request failed: {0}".format(str(exc))) from exc

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            self._raise_mapped_error(message=message, status_code=response.status_code)
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("error")
                if isinstance(message, str):
                    return message
            return response.text
        except ValueError:
            return response.text

    def _raise_mapped_error(self, message: str, status_code: int) -> None:
        normalized = (message or "").lower()
        if "insufficient" in normalized and ("buying power" in normalized or "fund" in normalized):
            raise InsufficientFundsError(message)
        if "market" in normalized and ("closed" in normalized or "hours" in normalized):
            raise MarketClosedError(message)
        if ("invalid symbol" in normalized) or ("symbol" in normalized and "not found" in normalized):
            raise InvalidSymbolError(message)
        raise ExternalAPIError("Alpaca API error ({0}): {1}".format(status_code, message))
