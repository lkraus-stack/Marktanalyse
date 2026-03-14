from __future__ import annotations


class ServiceError(Exception):
    """Base exception for external service integrations."""


class ExternalAPIError(ServiceError):
    """Raised when an external API request fails."""


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
