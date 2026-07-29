import asyncio
import time
import unittest

from app.jobs import AsyncJobStore
from backend.tests.fakes import CountingAsyncRunner


class JobAdversarialTest(unittest.IsolatedAsyncioTestCase):
    async def test_ten_duplicate_starts_create_one_job_and_one_runner(self):
        gate = asyncio.Event()
        runner = CountingAsyncRunner(result={"ok": True}, gate=gate)
        store = AsyncJobStore(max_concurrency=1)

        created = [
            store.start("plan", runner, dedupe_key="same-body")
            for _ in range(10)
        ]
        for _ in range(20):
            if runner.call_count:
                break
            await asyncio.sleep(0)

        self.assertEqual(len({item["id"] for item in created}), 1)
        self.assertEqual(len(store._jobs), 1)
        self.assertEqual(runner.call_count, 1)

        gate.set()
        await store.wait(created[0]["id"])
        self.assertEqual(store.get(created[0]["id"])["status"], "completed")

    async def test_timeout_and_cancel_are_failed_terminal_and_release_slot(self):
        never = CountingAsyncRunner(gate=asyncio.Event())
        next_runner = CountingAsyncRunner(result={"next": True})
        store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=0.01,
        )

        timed_out = store.start("plan", never)
        await store.wait(timed_out["id"])
        timeout_state = store.get(timed_out["id"])
        self.assertEqual(timeout_state["status"], "failed")
        self.assertEqual(timeout_state["error"]["code"], "JOB_TIMEOUT")
        self.assertIsNone(timeout_state["result"])

        running = store.start("plan", never, timeout_seconds=1)
        while store.get(running["id"])["status"] == "queued":
            await asyncio.sleep(0)
        self.assertTrue(store.cancel(running["id"]))
        await store.wait(running["id"])
        cancelled = store.get(running["id"])
        self.assertEqual(cancelled["status"], "failed")
        self.assertEqual(cancelled["error"]["code"], "JOB_CANCELLED")

        next_job = store.start("plan", next_runner, timeout_seconds=0.2)
        await store.wait(next_job["id"])
        self.assertEqual(store.get(next_job["id"])["status"], "completed")
        self.assertEqual(next_runner.call_count, 1)

    async def test_terminal_state_rejects_late_progress_and_result(self):
        started = asyncio.Event()
        swallowed = asyncio.Event()

        async def zombie(progress):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                progress("late", "must not overwrite")
                swallowed.set()
                return {"late": True}

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", zombie)
        await started.wait()
        self.assertTrue(store.cancel(created["id"]))
        await swallowed.wait()
        await store.wait(created["id"])

        terminal = store.get(created["id"])
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["phase"], "failed")
        self.assertEqual(terminal["error"]["code"], "JOB_CANCELLED")
        self.assertIsNone(terminal["result"])

    async def test_long_poll_wakes_on_version_change(self):
        started = asyncio.Event()
        advance = asyncio.Event()

        async def runner(progress):
            started.set()
            await advance.wait()
            progress("audit", "changed")
            return {"ok": True}

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)
        await started.wait()
        version = store.get(created["id"])["version"]
        waiting = asyncio.create_task(
            store.wait_for_update(
                created["id"],
                version,
                timeout_seconds=25,
            )
        )
        advance.set()
        changed = await asyncio.wait_for(waiting, timeout=0.2)

        self.assertGreater(changed["version"], version)
        await store.wait(created["id"])

    async def test_zero_second_long_poll_returns_immediately(self):
        gate = asyncio.Event()
        runner = CountingAsyncRunner(result={"ok": True}, gate=gate)
        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)
        while store.get(created["id"])["status"] == "queued":
            await asyncio.sleep(0)
        current = store.get(created["id"])

        started_at = time.monotonic()
        returned = await asyncio.wait_for(
            store.wait_for_update(
                created["id"],
                current["version"],
                timeout_seconds=0,
            ),
            timeout=0.2,
        )

        self.assertLess(time.monotonic() - started_at, 0.1)
        self.assertEqual(returned["version"], current["version"])
        store.cancel(created["id"])
        gate.set()
        await store.wait(created["id"])


if __name__ == "__main__":
    unittest.main()
