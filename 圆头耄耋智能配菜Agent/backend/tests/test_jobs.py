import asyncio
import time
import unittest

from app.jobs import AsyncJobStore


class AsyncJobStoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_returns_before_runner_finishes_and_polling_gets_result(self):
        runner_started = asyncio.Event()
        allow_finish = asyncio.Event()

        async def runner(progress):
            progress("planning", "耄耋正在设计菜品")
            runner_started.set()
            await allow_finish.wait()
            return {"title": "测试菜单"}

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)

        self.assertEqual(created["status"], "queued")
        self.assertIsNone(created["result"])

        await asyncio.wait_for(runner_started.wait(), timeout=1)
        running = store.get(created["id"])
        self.assertEqual(running["status"], "running")
        self.assertEqual(running["phase"], "planning")

        allow_finish.set()
        await store.wait(created["id"])

        completed = store.get(created["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"], {"title": "测试菜单"})

    async def test_duplicate_inflight_jobs_return_the_same_job(self):
        first_started = asyncio.Event()
        allow_first_finish = asyncio.Event()
        runner_calls = 0

        async def first_runner(progress):
            nonlocal runner_calls
            runner_calls += 1
            progress("planning", "第一个任务")
            first_started.set()
            await allow_first_finish.wait()
            return {"order": 1}

        store = AsyncJobStore(max_concurrency=1)
        first = store.start("plan", first_runner, dedupe_key="same-request")
        duplicate = store.start("plan", first_runner, dedupe_key="same-request")

        await asyncio.wait_for(first_started.wait(), timeout=1)
        self.assertEqual(duplicate["id"], first["id"])
        self.assertEqual(runner_calls, 1)

        allow_first_finish.set()
        await store.wait(first["id"])

    async def test_long_poll_returns_as_soon_as_job_progress_changes(self):
        runner_started = asyncio.Event()
        advance_runner = asyncio.Event()

        async def runner(progress):
            runner_started.set()
            await advance_runner.wait()
            progress("audit", "正在做合格检查")
            await asyncio.sleep(0)
            return {"done": True}

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)
        await asyncio.wait_for(runner_started.wait(), timeout=1)
        running = store.get(created["id"])

        waiting = asyncio.create_task(
            store.wait_for_update(
                created["id"],
                after_version=running["version"],
                timeout_seconds=1,
            )
        )
        advance_runner.set()
        changed = await asyncio.wait_for(waiting, timeout=1)

        self.assertGreater(changed["version"], running["version"])
        self.assertIn(changed["phase"], {"audit", "completed"})

    async def test_runner_timeout_enters_failed_terminal_state(self):
        async def runner(_progress):
            await asyncio.Event().wait()

        store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=0.02,
        )
        created = store.start("plan", runner)
        await store.wait(created["id"])

        failed = store.get(created["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "JOB_TIMEOUT")
        self.assertTrue(failed["error"]["retryable"])
        self.assertIsNone(failed["result"])

    async def test_timeout_does_not_wait_for_runner_that_swallows_cancel(self):
        zombie_finished = asyncio.Event()

        async def zombie_runner(_progress):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)
                zombie_finished.set()
                return {"late": True}

        next_called = asyncio.Event()

        async def next_runner(_progress):
            next_called.set()
            return {"next": True}

        store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=0.01,
        )
        zombie = store.start("plan", zombie_runner)
        await asyncio.wait_for(store.wait(zombie["id"]), timeout=0.03)

        failed = store.get(zombie["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "JOB_TIMEOUT")

        next_job = store.start(
            "plan",
            next_runner,
            timeout_seconds=0.2,
        )
        await asyncio.wait_for(store.wait(next_job["id"]), timeout=0.03)
        self.assertTrue(next_called.is_set())
        self.assertFalse(zombie_finished.is_set())
        self.assertEqual(store.get(next_job["id"])["status"], "completed")

        await asyncio.wait_for(zombie_finished.wait(), timeout=0.1)
        self.assertEqual(store.get(zombie["id"])["status"], "failed")

    async def test_job_does_not_start_after_absolute_deadline_passed(self):
        runner_called = False

        async def runner(_progress):
            nonlocal runner_called
            runner_called = True
            return {"late": True}

        store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=0.001,
        )
        created = store.start("plan", runner)
        time.sleep(0.02)
        await store.wait(created["id"])

        failed = store.get(created["id"])
        self.assertFalse(runner_called)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "JOB_TIMEOUT")

    async def test_timeout_includes_waiting_for_semaphore_and_releases_slot(self):
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def first_runner(_progress):
            first_started.set()
            await release_first.wait()
            return {"first": True}

        second_called = False

        async def second_runner(_progress):
            nonlocal second_called
            second_called = True
            return {"second": True}

        third_called = False

        async def third_runner(_progress):
            nonlocal third_called
            third_called = True
            return {"third": True}

        store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=1,
        )
        first = store.start("plan", first_runner)
        await asyncio.wait_for(first_started.wait(), timeout=1)
        second = store.start(
            "plan",
            second_runner,
            timeout_seconds=0.02,
        )
        await store.wait(second["id"])

        self.assertFalse(second_called)
        failed = store.get(second["id"])
        self.assertEqual(failed["error"]["code"], "JOB_TIMEOUT")

        release_first.set()
        await store.wait(first["id"])
        third = store.start("plan", third_runner)
        await store.wait(third["id"])
        self.assertTrue(third_called)
        self.assertEqual(store.get(third["id"])["status"], "completed")

    async def test_running_job_cancellation_enters_failed_terminal_state(self):
        runner_started = asyncio.Event()

        async def runner(_progress):
            runner_started.set()
            await asyncio.Event().wait()

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)
        await asyncio.wait_for(runner_started.wait(), timeout=1)

        self.assertTrue(store.cancel(created["id"]))
        await store.wait(created["id"])

        failed = store.get(created["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "JOB_CANCELLED")
        self.assertTrue(failed["error"]["retryable"])
        self.assertFalse(store.cancel(created["id"]))

    async def test_cancelled_runner_cannot_overwrite_terminal_state(self):
        runner_started = asyncio.Event()
        runner_finished = asyncio.Event()

        async def runner(progress):
            runner_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                progress("late-progress", "不应覆盖取消终态")
                runner_finished.set()
                return {"late": True}

        store = AsyncJobStore(max_concurrency=1)
        created = store.start("plan", runner)
        await asyncio.wait_for(runner_started.wait(), timeout=1)
        self.assertTrue(store.cancel(created["id"]))
        await asyncio.wait_for(runner_finished.wait(), timeout=1)
        await store.wait(created["id"])

        failed = store.get(created["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["phase"], "failed")
        self.assertEqual(failed["error"]["code"], "JOB_CANCELLED")
        self.assertIsNone(failed["result"])

    async def test_terminal_job_expires_after_ttl(self):
        async def runner(_progress):
            return {"done": True}

        store = AsyncJobStore(
            max_concurrency=1,
            ttl_seconds=0.01,
        )
        created = store.start("plan", runner)
        await store.wait(created["id"])
        self.assertIsNotNone(store.get(created["id"]))

        await asyncio.sleep(0.02)
        self.assertIsNone(store.get(created["id"]))


if __name__ == "__main__":
    unittest.main()
