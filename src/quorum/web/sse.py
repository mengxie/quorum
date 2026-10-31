"""Server-Sent Events: one long-lived HTTP response per open screen."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable


async def change_stream(
    changes: asyncio.Queue[None],
    is_disconnected: Callable[[], Awaitable[bool]],
    *,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Emits `changed` whenever the event changes, and a comment every few seconds so that
    proxies keep the connection open. The page then fetches fresh HTML: the stream carries a
    signal, never data, so it can never show something a normal request would not."""
    yield "retry: 3000\n\n"
    while not await is_disconnected():
        try:
            await asyncio.wait_for(changes.get(), timeout=heartbeat_seconds)
        except TimeoutError:
            yield ": keep-alive\n\n"
        else:
            yield "event: changed\ndata: {}\n\n"
