import asyncio
import unittest

from app.channels import RecipeChannelService, find_channel
from app.jobs import AsyncJobStore
from app.kimi import AppError
from app.models import ChannelSwapResult
from backend.tests.test_channel_service import (
    _recipe_variant,
    _source,
    _swap,
    _two_channel_plan,
)


class ChannelSwapAdversarialTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.block = False
        self.counter = 0

        async def swap_factory(
            channel_id,
            budget,
            current,
            _constraints,
            _api_key,
        ):
            self.calls.append(
                {
                    "channel_id": channel_id,
                    "budget": tuple(
                        (item.id, item.estimatedGrams) for item in budget
                    ),
                    "current_id": current.id,
                }
            )
            self.started.set()
            if self.block:
                await self.gate.wait()
            self.counter += 1
            return _recipe_variant(current, self.counter)

        self.jobs = AsyncJobStore(max_concurrency=1, job_timeout_seconds=2)
        self.service = RecipeChannelService(
            self.jobs,
            swap_recipe_factory=swap_factory,
        )
        self.plan = self.service.register_plan(
            _two_channel_plan(),
            _source(),
        )

    async def _result(self, job_id: str) -> ChannelSwapResult:
        await self.jobs.wait(job_id)
        envelope = self.jobs.get(job_id)
        self.assertEqual(envelope["status"], "completed", envelope)
        return ChannelSwapResult.model_validate(envelope["result"])

    async def test_busy_same_and_other_channel_create_no_job_or_model_call(self):
        self.block = True
        owner = self.service.begin_swap(
            _swap(self.plan, "channel-a", "owner"),
            "fake-key",
        )
        await self.started.wait()
        job_count = len(self.jobs._jobs)

        for channel_id in ("channel-a", "channel-b"):
            with self.subTest(channel_id=channel_id), self.assertRaises(
                AppError
            ) as caught:
                self.service.begin_swap(
                    _swap(self.plan, channel_id, f"blocked-{channel_id}"),
                    "fake-key",
                )
            self.assertEqual(caught.exception.code, "REPLACEMENT_BUSY")
            self.assertEqual(len(self.jobs._jobs), job_count)
            self.assertEqual(len(self.calls), 1)

        self.gate.set()
        await self._result(owner.id)

    async def test_a_then_b_keep_separate_original_budgets(self):
        original_a = find_channel(self.plan, "channel-a").ingredientBudget
        original_b = find_channel(self.plan, "channel-b").ingredientBudget

        first = self.service.begin_swap(
            _swap(self.plan, "channel-a", "first"),
            "fake-key",
        )
        after_a = (await self._result(first.id)).plan
        second = self.service.begin_swap(
            _swap(after_a, "channel-b", "second"),
            "fake-key",
        )
        after_b = (await self._result(second.id)).plan

        self.assertEqual(
            self.calls[0]["budget"],
            tuple((item.id, item.estimatedGrams) for item in original_a),
        )
        self.assertEqual(
            self.calls[1]["budget"],
            tuple((item.id, item.estimatedGrams) for item in original_b),
        )
        self.assertEqual(
            find_channel(after_b, "channel-a").ingredientBudget,
            original_a,
        )
        self.assertEqual(
            find_channel(after_b, "channel-b").ingredientBudget,
            original_b,
        )
