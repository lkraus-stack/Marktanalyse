from __future__ import annotations

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from typing import Optional

from config import get_settings

logger = logging.getLogger("market_intelligence.services.email")


class EmailService:
    """SMTP-based e-mail delivery for alert notifications."""

    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._from_email = settings.smtp_from_email or settings.smtp_username
        self._use_tls = settings.smtp_use_tls
        self._retries = max(0, settings.alert_delivery_retries)

    def is_configured(self) -> bool:
        """Return True when SMTP credentials are present."""
        return bool(self._username and self._password and self._from_email)

    async def send_alert_email(
        self,
        subject: str,
        alert_title: str,
        message: str,
        to_email: Optional[str] = None,
    ) -> bool:
        """Send one alert mail with retries."""
        if not self.is_configured():
            logger.warning("SMTP not configured, skipping email delivery.", extra={"event": "email_not_configured"})
            return False

        recipient = to_email or self._username
        if not recipient:
            return False

        html = self._build_html(alert_title=alert_title, message=message)
        for attempt in range(self._retries + 1):
            try:
                await asyncio.to_thread(
                    self._send_sync,
                    subject,
                    recipient,
                    html,
                )
                return True
            except Exception:
                logger.exception(
                    "Alert email delivery failed.",
                    extra={"event": "email_delivery_failed", "attempt": str(attempt + 1)},
                )
                if attempt < self._retries:
                    await asyncio.sleep(min(8, 2**attempt))
        return False

    def _send_sync(self, subject: str, recipient: str, html: str) -> None:
        if not self._from_email:
            raise ValueError("SMTP from address is not configured.")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from_email
        msg["To"] = recipient
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self._host, self._port, timeout=20) as server:
            server.ehlo()
            if self._use_tls:
                server.starttls()
                server.ehlo()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.sendmail(self._from_email, [recipient], msg.as_string())

    def _build_html(self, alert_title: str, message: str) -> str:
        return """
<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; background: #0b1220; color: #f8fafc; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; border: 1px solid #334155; border-radius: 10px; padding: 20px; background: #111827;">
      <h2 style="margin-top: 0; color: #60a5fa;">{title}</h2>
      <p style="line-height: 1.5;">{body}</p>
      <p style="font-size: 12px; color: #94a3b8; margin-top: 24px;">
        Diese Nachricht wurde vom Markt-Intelligence Alert-System erzeugt.
      </p>
    </div>
  </body>
</html>
""".format(
            title=self._escape_html(alert_title),
            body=self._escape_html(message).replace("\n", "<br/>"),
        )

    def _escape_html(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
