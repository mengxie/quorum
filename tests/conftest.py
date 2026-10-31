import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from quorum.application.service import QuorumService
from quorum.config import Settings
from quorum.infrastructure.database import Pool, create_pool, migrate
from quorum.infrastructure.notifications import ChangeHub, InProcessNotifier
from quorum.infrastructure.repository import PostgresRepository
from quorum.web.app import create_app

# Database tests run whenever this is set, as it always is in CI.
DATABASE_URL = os.environ.get("QUORUM_TEST_DATABASE_URL")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture(scope="session")
async def pool() -> AsyncIterator[Pool]:
    if DATABASE_URL is None:
        pytest.skip("Set QUORUM_TEST_DATABASE_URL to run database tests.")
    pool = await create_pool(DATABASE_URL)
    await migrate(pool)
    yield pool
    await pool.close()


@pytest.fixture
async def db(pool: Pool) -> Pool:
    await pool.execute("TRUNCATE events CASCADE")
    return pool


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def hub() -> ChangeHub:
    return ChangeHub()


@pytest.fixture
def service(db: Pool, clock: Clock, hub: ChangeHub) -> QuorumService:
    return QuorumService(PostgresRepository(db), InProcessNotifier(hub), clock=clock)


@pytest.fixture
async def client(db: Pool) -> AsyncIterator[httpx.AsyncClient]:
    assert DATABASE_URL is not None
    app = create_app(Settings(database_url=DATABASE_URL, secret_key="test-" + "x" * 40))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client
