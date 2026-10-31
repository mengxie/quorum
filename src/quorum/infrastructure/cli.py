"""`quorum-migrate`: apply database migrations from a deploy step instead of at app startup."""

import asyncio

from quorum.config import Settings
from quorum.infrastructure.database import create_pool, migrate


async def _run() -> list[str]:
    settings = Settings()  # values come from QUORUM_* environment variables
    pool = await create_pool(settings.database_url)
    try:
        return await migrate(pool)
    finally:
        await pool.close()


def migrate_command() -> None:
    applied = asyncio.run(_run())
    print("Applied:", ", ".join(applied) if applied else "nothing, already up to date")  # noqa: T201
