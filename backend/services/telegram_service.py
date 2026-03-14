from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger("market_intelligence.services.telegram")


class TelegramService:
    """Telegram Bot API delivery for alert notifications."""

    # Setup:
    # 1) In Telegram @BotFather einen Bot erstellen und Token kopieren.
    # 2) Dem Bot eine Nachricht senden.
    # 3) Chat-ID ermitteln (z. B. via getUpdates API).
    # 4) TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID in .env setzen.

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.telegram_bot_token
        self._default_chat_id = settings.telegram_chat_id
        self._retries = max(0, settings.alert_delivery_retries)
        self._client = httpx.AsyncClient(timeout=15.0)

    def is_configured(self) -> bool:
        """Return True if token and default chat are configured."""
        return bool(self._token and self._default_chat_id)

    async def send_alert_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Send one Telegram message with retry semantics."""
        if not self._token:
            logger.warning("Telegram token missing, skipping delivery.", extra={"event": "telegram_not_configured"})
            return False

        target_chat = chat_id or self._default_chat_id
        if not target_chat:
            return False

        url = "https://api.telegram.org/bot{0}/sendMessage".format(self._token)
        payload = {
            "chat_id": target_chat,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        for attempt in range(self._retries + 1):
            try:
                response = await self._client.post(url, json=payload)
                response.raise_for_status()
                response_payload = response.json()
                if response_payload.get("ok") is not True:
                    raise ValueError("Telegram API returned non-ok response.")
                return True
            except Exception:
                logger.exception(
                    "Telegram delivery failed.",
                    extra={"event": "telegram_delivery_failed", "attempt": str(attempt + 1)},
                )
                if attempt < self._retries:
                    await asyncio.sleep(min(8, 2**attempt))
        return False

    async def close(self) -> None:
        """Release underlying HTTP resources."""
        await self._client.aclose()
