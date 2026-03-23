from __future__ import annotations

import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import AsyncSessionLocal, create_tables
from services.default_assets import seed_default_assets


async def seed_assets() -> None:
    """Create tables and seed default tracked assets."""
    await create_tables()

    async with AsyncSessionLocal() as session:
        summary = await seed_default_assets(session)
        if summary["seeded_count"] == 0:
            print("Seed abgeschlossen: keine neuen Assets eingefuegt.")
            return

        print(f"Seed abgeschlossen: {summary['seeded_count']} Assets eingefuegt.")


def main() -> None:
    """Entry point for CLI execution."""
    asyncio.run(seed_assets())


if __name__ == "__main__":
    main()
