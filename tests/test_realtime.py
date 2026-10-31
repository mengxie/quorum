import asyncio
from uuid import uuid4

import pytest

from quorum.infrastructure.database import Pool
from quorum.infrastructure.notifications import ChangeHub, PostgresNotifier
from quorum.web.sse import change_stream
from tests.conftest import DATABASE_URL


async def test_hub_collapses_bursts_into_one_signal_and_cleans_up() -> None:
    hub = ChangeHub()
    event_id = uuid4()
    with hub.subscribe(event_id) as changes:
        hub.notify(event_id)
        hub.notify(event_id)
        assert changes.qsize() == 1
        assert hub.subscriber_count(event_id) == 1
    assert hub.subscriber_count(event_id) == 0
    hub.notify(event_id)  # nobody listening: a no-op


async def test_stream_sends_changes_heartbeats_and_stops_on_disconnect() -> None:
    changes: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    stream = change_stream(changes, is_disconnected, heartbeat_seconds=0.01)
    assert await anext(stream) == "retry: 3000\n\n"
    assert await anext(stream) == ": keep-alive\n\n"
    changes.put_nowait(None)
    assert await anext(stream) == "event: changed\ndata: {}\n\n"
    disconnected = True
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_a_change_published_by_one_instance_reaches_another(db: Pool) -> None:
    assert DATABASE_URL is not None
    hub_a, hub_b = ChangeHub(), ChangeHub()
    instance_a = PostgresNotifier(db, DATABASE_URL, hub_a)
    instance_b = PostgresNotifier(db, DATABASE_URL, hub_b)
    await instance_a.start()
    await instance_b.start()
    try:
        event_id = uuid4()
        with hub_b.subscribe(event_id) as changes:
            await instance_a.publish(event_id)
            await asyncio.wait_for(changes.get(), timeout=5)
    finally:
        await instance_a.stop()
        await instance_b.stop()
