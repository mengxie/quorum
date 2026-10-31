"""Real-time fan-out.

Every change publishes "event X changed". The ChangeHub wakes the Server-Sent Events
connections held by this process; PostgresNotifier carries the signal between processes with
LISTEN/NOTIFY, so several app instances behind a load balancer stay in sync without Redis.
"""

import asyncio
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import asyncpg

from quorum.infrastructure.database import Pool

CHANNEL = "quorum_changes"


class ChangeHub:
    def __init__(self) -> None:
        self._subscribers: defaultdict[UUID, set[asyncio.Queue[None]]] = defaultdict(set)

    @contextmanager
    def subscribe(self, event_id: UUID) -> Iterator[asyncio.Queue[None]]:
        # Capacity one: a burst of changes collapses into a single "go and refresh" signal.
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers[event_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[event_id].discard(queue)
            if not self._subscribers[event_id]:
                del self._subscribers[event_id]

    def notify(self, event_id: UUID) -> None:
        for queue in self._subscribers.get(event_id, ()):
            if queue.empty():
                queue.put_nowait(None)

    def subscriber_count(self, event_id: UUID) -> int:
        return len(self._subscribers.get(event_id, ()))


class InProcessNotifier:
    """For a single process (and tests): publish straight to the local hub."""

    def __init__(self, hub: ChangeHub) -> None:
        self._hub = hub

    async def publish(self, event_id: UUID) -> None:
        self._hub.notify(event_id)


class PostgresNotifier:
    def __init__(self, pool: Pool, dsn: str, hub: ChangeHub) -> None:
        self._pool = pool
        self._dsn = dsn
        self._hub = hub
        self._listener: asyncpg.Connection[asyncpg.Record] | None = None

    async def start(self) -> None:
        self._listener = await asyncpg.connect(self._dsn)
        await self._listener.add_listener(CHANNEL, self._received)

    async def stop(self) -> None:
        if self._listener is not None:
            await self._listener.remove_listener(CHANNEL, self._received)
            await self._listener.close()
            self._listener = None

    async def publish(self, event_id: UUID) -> None:
        await self._pool.execute("SELECT pg_notify($1, $2)", CHANNEL, str(event_id))

    def _received(self, _connection: object, _pid: int, _channel: str, payload: object) -> None:
        try:
            event_id = UUID(str(payload))
        except ValueError:
            return
        self._hub.notify(event_id)
