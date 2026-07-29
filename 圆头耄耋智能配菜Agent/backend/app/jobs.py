import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel

from .kimi import AppError


logger = logging.getLogger("uvicorn.error")
ProgressCallback = Callable[[str, str], None]
JobRunner = Callable[[ProgressCallback], Awaitable[Any]]
JobFailureCallback = Callable[[str, Dict[str, Any]], None]


class AsyncJobStore:
    def __init__(
        self,
        max_concurrency: int = 1,
        ttl_seconds: float = 1800,
        job_timeout_seconds: float = 900,
    ) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._failure_callbacks: Dict[str, JobFailureCallback] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._ttl_seconds = ttl_seconds
        self._job_timeout_seconds = job_timeout_seconds

    def start(
        self,
        kind: str,
        runner: JobRunner,
        dedupe_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        on_failure: Optional[JobFailureCallback] = None,
    ) -> Dict[str, Any]:
        self._cleanup()
        if dedupe_key:
            for existing_id, existing in self._jobs.items():
                if (
                    existing["kind"] == kind
                    and existing.get("dedupeKey") == dedupe_key
                    and existing["status"] in {"queued", "running"}
                ):
                    return self.get(existing_id)

        job_id = uuid4().hex
        now = time.monotonic()
        self._jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "phase": "queued",
            "message": "任务已排队，耄耋马上开工。",
            "result": None,
            "error": None,
            "dedupeKey": dedupe_key,
            "timeoutSeconds": (
                self._job_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
            "version": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        self._events[job_id] = asyncio.Event()
        if on_failure is not None:
            self._failure_callbacks[job_id] = on_failure
        self._tasks[job_id] = asyncio.create_task(self._run(job_id, runner))
        return self.get(job_id)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._cleanup()
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            key: value
            for key, value in job.items()
            if key
            not in {
                "createdAt",
                "updatedAt",
                "dedupeKey",
                "timeoutSeconds",
            }
        }

    async def wait_for_update(
        self,
        job_id: str,
        after_version: int,
        timeout_seconds: float = 25,
    ) -> Optional[Dict[str, Any]]:
        current = self.get(job_id)
        if current is None or current["version"] > after_version:
            return current

        event = self._events.get(job_id)
        current = self.get(job_id)
        if current is None or current["version"] > after_version:
            return current
        if event is None:
            return current

        bounded_timeout = max(0.0, min(timeout_seconds, 25.0))
        if bounded_timeout == 0:
            return self.get(job_id)
        try:
            await asyncio.wait_for(
                event.wait(),
                timeout=bounded_timeout,
            )
        except asyncio.TimeoutError:
            pass
        return self.get(job_id)

    async def wait(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                return

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job["status"] not in {"queued", "running"}:
            return False
        self._fail(
            job_id,
            code="JOB_CANCELLED",
            message="任务已经取消，可以重新提交。",
            retryable=True,
        )
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        return True

    @staticmethod
    def _consume_background_task(task: asyncio.Task) -> None:
        try:
            task.result()
        except BaseException:
            return

    async def _run(self, job_id: str, runner: JobRunner) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        timeout_seconds = max(0.001, float(job["timeoutSeconds"]))
        deadline = job["createdAt"] + timeout_seconds
        acquired = False
        runner_task: Optional[asyncio.Task] = None
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._fail(
                    job_id,
                    code="JOB_TIMEOUT",
                    message="耄耋处理太久了，请重新提交。",
                    retryable=True,
                )
                return
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=remaining,
            )
            acquired = True
            job = self._jobs.get(job_id)
            if job is None or job["status"] != "queued":
                return
            if time.monotonic() >= deadline:
                self._fail(
                    job_id,
                    code="JOB_TIMEOUT",
                    message="耄耋处理太久了，请重新提交。",
                    retryable=True,
                )
                return
            self._update(
                job_id,
                status="running",
                phase="starting",
                message="耄耋开始处理。",
            )

            def progress(phase: str, message: str) -> None:
                current = self._jobs.get(job_id)
                if current is None or current["status"] != "running":
                    return
                self._update(job_id, phase=phase, message=message)

            runner_task = asyncio.create_task(runner(progress))
            remaining = max(0.0, deadline - time.monotonic())
            done, _ = await asyncio.wait(
                {runner_task},
                timeout=remaining,
            )
            if runner_task not in done:
                self._fail(
                    job_id,
                    code="JOB_TIMEOUT",
                    message="耄耋处理太久了，请重新提交。",
                    retryable=True,
                )
                runner_task.cancel()
                return

            result = runner_task.result()
            current = self._jobs.get(job_id)
            if current is None or current["status"] != "running":
                return
            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json")
            self._update(
                job_id,
                status="completed",
                phase="completed",
                message="菜单做好了。",
                result=result,
                error=None,
            )
            self._failure_callbacks.pop(job_id, None)
        except asyncio.TimeoutError:
            self._fail(
                job_id,
                code="JOB_TIMEOUT",
                message="耄耋处理太久了，请重新提交。",
                retryable=True,
            )
        except asyncio.CancelledError:
            job = self._jobs.get(job_id)
            if job is not None and job["status"] in {"queued", "running"}:
                self._fail(
                    job_id,
                    code="JOB_CANCELLED",
                    message="任务已经取消，可以重新提交。",
                    retryable=True,
                )
        except AppError as exc:
            self._fail(
                job_id,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
            )
        except Exception:
            logger.exception("Unexpected async job failure: job_id=%s", job_id)
            self._fail(
                job_id,
                code="JOB_FAILED",
                message="耄耋这次没接住，请重新生成。",
                retryable=True,
            )
        finally:
            if runner_task is not None and not runner_task.done():
                runner_task.cancel()
                runner_task.add_done_callback(
                    self._consume_background_task
                )
            if acquired:
                self._semaphore.release()

    def _fail(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None or job["status"] in {"completed", "failed"}:
            return
        error = {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
        self._update(
            job_id,
            status="failed",
            phase="failed",
            message=message,
            result=None,
            error=error,
        )
        callback = self._failure_callbacks.pop(job_id, None)
        if callback is not None:
            try:
                callback(job_id, error)
            except Exception:
                logger.exception(
                    "Async job failure callback failed: job_id=%s",
                    job_id,
                )

    def _update(self, job_id: str, **changes: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        if job["status"] in {"completed", "failed"}:
            return
        job.update(changes)
        job["version"] += 1
        job["updatedAt"] = time.monotonic()
        event = self._events.get(job_id)
        if event is not None:
            event.set()
        self._events[job_id] = asyncio.Event()

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job["status"] in {"completed", "failed"}
            and now - job["updatedAt"] > self._ttl_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
            self._tasks.pop(job_id, None)
            self._events.pop(job_id, None)
            self._failure_callbacks.pop(job_id, None)
