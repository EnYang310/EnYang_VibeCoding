import asyncio
from contextlib import suppress
from typing import Awaitable, Protocol, TypeVar


class DisconnectAwareRequest(Protocol):
    async def is_disconnected(self) -> bool: ...


class ClientDisconnected(Exception):
    """The caller navigated away, so no paid work should continue for it."""


T = TypeVar("T")


async def await_while_connected(
    request: DisconnectAwareRequest,
    work: Awaitable[T],
    *,
    poll_interval: float = 0.2,
) -> T:
    """Cancel an async provider call as soon as its browser client disconnects."""
    task = asyncio.create_task(work)
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=poll_interval)
            if task.done():
                break
            if await request.is_disconnected():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise ClientDisconnected
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
