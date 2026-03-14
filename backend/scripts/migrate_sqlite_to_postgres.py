from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from database import Base
import models  # noqa: F401


def normalize_url(raw_url: str) -> str:
    """Normalize database URL for SQLAlchemy async drivers."""
    url = raw_url.strip()
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://{0}".format(url[len("postgresql://") :])
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://{0}".format(url[len("postgres://") :])
    return url


async def copy_table_data(
    source_engine: AsyncEngine,
    target_engine: AsyncEngine,
    table_name: str,
    truncate_target: bool,
    chunk_size: int,
) -> int:
    """Copy one table from source to target."""
    table = Base.metadata.tables[table_name]
    rows: List[Dict[str, Any]] = []
    async with source_engine.connect() as source_conn:
        result = await source_conn.execute(select(table))
        for row in result:
            rows.append(dict(row._mapping))

    async with target_engine.begin() as target_conn:
        if truncate_target:
            await target_conn.execute(delete(table))
        if not rows:
            return 0
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            await target_conn.execute(table.insert(), chunk)
    return len(rows)


async def run_migration(
    source_url: str,
    target_url: str,
    truncate_target: bool,
    chunk_size: int,
) -> None:
    """Copy all SQLAlchemy tables from SQLite source to PostgreSQL target."""
    normalized_source = normalize_url(source_url)
    normalized_target = normalize_url(target_url)
    source_engine = create_async_engine(normalized_source, future=True)
    target_engine = create_async_engine(normalized_target, future=True, pool_pre_ping=True)
    try:
        async with target_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        for table in Base.metadata.sorted_tables:
            copied = await copy_table_data(
                source_engine=source_engine,
                target_engine=target_engine,
                table_name=table.name,
                truncate_target=truncate_target,
                chunk_size=max(1, chunk_size),
            )
            print("copied {0} rows -> {1}".format(copied, table.name))
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLAlchemy data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--source-url",
        required=True,
        help="Source DB URL (example: sqlite+aiosqlite:///./market_intelligence.db)",
    )
    parser.add_argument(
        "--target-url",
        required=True,
        help="Target DB URL (example: postgresql://user:pass@host/db?sslmode=require)",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete existing rows in target tables before import.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Insert chunk size for batch inserts (default: 500).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_migration(
            source_url=args.source_url,
            target_url=args.target_url,
            truncate_target=bool(args.truncate_target),
            chunk_size=int(args.chunk_size),
        )
    )


if __name__ == "__main__":
    main()
