"""Connection pool and migrations."""

from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).parent / "migrations"
MIGRATION_LOCK = 0x51_55_4F_52  # "QUOR"

type Pool = asyncpg.Pool[asyncpg.Record]


async def create_pool(dsn: str) -> Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=10)


async def migrate(pool: Pool) -> list[str]:
    """Applies new SQL scripts in order, once each, under a lock so instances can start together."""
    applied: list[str] = []
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", MIGRATION_LOCK)
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {
            row["version"]
            for row in await connection.fetch("SELECT version FROM schema_migrations")
        }
        for script in sorted(MIGRATIONS.glob("*.sql")):
            if script.stem in done:
                continue
            await connection.execute(script.read_text(encoding="utf-8"))
            await connection.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1)", script.stem
            )
            applied.append(script.stem)
    return applied
