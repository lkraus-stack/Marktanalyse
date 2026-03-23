from __future__ import annotations


class ServiceError(Exception):
    """Base exception for external service integrations."""


class ExternalAPIError(ServiceError):
    """Raised when an external API request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        provider: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        attempts: list[object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.provider = provider
        self.endpoint = endpoint
        self.model = model
        self.attempts = attempts or []


class RateLimitExceededError(ServiceError):
    """Raised when a service-specific rate limit is hit."""


class InvalidSymbolError(ServiceError):
    """Raised when a symbol cannot be resolved by an API."""


class InsufficientFundsError(ExternalAPIError):
    """Raised when broker reports insufficient buying power/cash."""


class MarketClosedError(ExternalAPIError):
    """Raised when order submission is attempted outside market hours."""


class SafetyConstraintError(ServiceError):
    """Raised when live-trading safety constraints block execution."""
