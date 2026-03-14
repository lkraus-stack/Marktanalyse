from __future__ import annotations

from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()
logger = logging.getLogger("market_intelligence.database")


def _normalize_database_url(raw_url: str) -> str:
    """Normalize postgres URLs to asyncpg driver for SQLAlchemy async."""
    url = raw_url.strip()
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://{0}".format(url[len("postgresql://") :])
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://{0}".format(url[len("postgres://") :])
    return url


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


effective_database_url = settings.neon_database_url or settings.database_url

engine = create_async_engine(
    _normalize_database_url(effective_database_url),
    echo=False,
    future=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session dependency."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """Create all database tables from SQLAlchemy metadata."""
    import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("Database tables are ready.", extra={"event": "database_tables_ready"})
