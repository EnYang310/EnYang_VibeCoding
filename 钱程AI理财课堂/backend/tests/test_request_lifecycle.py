import asyncio

import pytest

from app.request_lifecycle import ClientDisconnected, await_while_connected


class DisconnectingRequest:
    async def is_disconnected(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_cancels_expensive_work_when_the_browser_leaves() -> None:
    cancelled = asyncio.Event()

    async def work() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(ClientDisconnected):
        await await_while_connected(DisconnectingRequest(), work(), poll_interval=0)

    assert cancelled.is_set()
