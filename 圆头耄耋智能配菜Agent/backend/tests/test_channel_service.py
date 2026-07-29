import asyncio
import unittest

from app.channels import RecipeChannelService, derive_channel_budget, find_channel
from app.jobs import AsyncJobStore
from app.kimi import AppError
from app.models import (
    ChannelSwapRequest,
    ChannelSwapResult,
    GeneratePlanRequest,
    IngredientInput,
    MealPlan,
    Recipe,
    RecipeDraft,
)
from backend.tests.test_recipe_channels import (
    valid_meal_plan_payload,
    valid_recipe_channel_payload,
)


def _source() -> GeneratePlanRequest:
    return GeneratePlanRequest(
        ingredients=[
            IngredientInput(
                id="tomato",
                name="番茄",
                amount=2,
                unit="个",
                estimatedGrams=200,
            ),
            IngredientInput(
                id="egg",
                name="鸡蛋",
                amount=2,
                unit="个",
                estimatedGrams=100,
            ),
            IngredientInput(
                id="beef",
                name="牛肉",
                amount=1,
                unit="份",
                estimatedGrams=250,
            ),
            IngredientInput(
                id="tofu-skin",
                name="豆皮",
                amount=1,
                unit="份",
                estimatedGrams=180,
            ),
        ],
        people=2,
        mealCount=1,
        tools=["炒锅", "汤锅"],
        avoid=[],
        flavor="清淡",
    )


def _two_channel_plan() -> MealPlan:
    payload = valid_meal_plan_payload()
    channel_a = valid_recipe_channel_payload("channel-a")
    channel_a["ingredientBudget"] = [
        _source().ingredients[0].model_dump(),
        _source().ingredients[1].model_dump(),
    ]
    channel_a["current"]["id"] = "recipe-a-current"
    channel_a["current"]["name"] = "番茄炒蛋"

    channel_b = valid_recipe_channel_payload("channel-b")
    channel_b["ingredientBudget"] = [
        _source().ingredients[2].model_dump(),
        _source().ingredients[3].model_dump(),
    ]
    channel_b["current"]["id"] = "recipe-b-current"
    channel_b["current"]["name"] = "牛肉烧豆皮"
    payload["meals"][0]["channels"] = [channel_a, channel_b]
    total = sum(item["current"]["totalKcal"] for item in (channel_a, channel_b))
    payload["meals"][0]["totalKcal"] = total
    payload["meals"][0]["perPersonKcal"] = round(total / payload["people"])
    payload["totalKcal"] = total
    payload["perPersonKcal"] = round(total / payload["people"])
    return MealPlan.model_validate(payload)


def _swap(
    plan: MealPlan,
    channel_id: str,
    suffix: str,
) -> ChannelSwapRequest:
    channel = find_channel(plan, channel_id)
    return ChannelSwapRequest(
        planId=plan.id,
        channelId=channel_id,
        planRevision=plan.revision,
        channelRevision=channel.revision,
        idempotencyKey=f"swap-{channel_id}-{suffix}-000000",
    )


def _recipe_variant(current: Recipe, index: int) -> Recipe:
    return current.model_copy(
        update={
            "id": f"recipe-swap-{index}",
            "name": f"{current.name}新做法{index}",
            "totalKcal": current.totalKcal + index,
        }
    )


class ChannelBudgetTest(unittest.TestCase):
    def test_budget_is_exact_current_allocation_and_is_immutable_tuple(self):
        source = _source()
        draft = RecipeDraft.model_validate(
            {
                "name": "番茄炒蛋",
                "description": "家常菜",
                "ingredients": [
                    {
                        "name": "番茄",
                        "nutritionQuery": "tomatoes raw",
                        "nutritionFallbackQuery": "tomatoes red raw",
                        "grams": 160,
                        "note": "",
                        "estimatedKcalPer100g": 18,
                    },
                    {
                        "name": "鸡蛋",
                        "nutritionQuery": "egg whole raw",
                        "nutritionFallbackQuery": "egg raw",
                        "grams": 90,
                        "note": "",
                        "estimatedKcalPer100g": 143,
                    },
                ],
                "seasonings": [],
                "steps": [{"title": "炒", "detail": "炒熟。", "minutes": 8}],
                "totalMinutes": 10,
                "difficulty": "简单",
                "lowCalorieReason": "少油。",
                "tools": ["炒锅"],
                "tags": [],
            }
        )

        budget = derive_channel_budget(draft, source)

        self.assertIsInstance(budget, tuple)
        self.assertEqual(
            [(item.id, item.estimatedGrams) for item in budget],
            [("tomato", 160), ("egg", 90)],
        )


class ChannelServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.release = asyncio.Event()
        self.factory_started = asyncio.Event()
        self.block = False
        self.fail = False
        self.counter = 0

        async def swap_factory(
            channel_id,
            budget,
            current,
            _constraints,
            _api_key,
        ):
            self.calls.append(
                (
                    channel_id,
                    tuple((item.id, item.estimatedGrams) for item in budget),
                    current.id,
                )
            )
            self.factory_started.set()
            if self.block:
                await self.release.wait()
            if self.fail:
                raise AppError("AI_TIMEOUT", "换菜超时。", 504, True)
            self.counter += 1
            return _recipe_variant(current, self.counter)

        self.job_store = AsyncJobStore(
            max_concurrency=1,
            job_timeout_seconds=2,
        )
        self.service = RecipeChannelService(
            self.job_store,
            swap_recipe_factory=swap_factory,
        )
        self.plan = self.service.register_plan(_two_channel_plan(), _source())

    async def _result(self, job_id: str) -> ChannelSwapResult:
        await self.job_store.wait(job_id)
        envelope = self.job_store.get(job_id)
        self.assertEqual(envelope["status"], "completed", envelope)
        return ChannelSwapResult.model_validate(envelope["result"])

    async def test_old_recipe_stays_visible_until_success_then_swaps_atomically(self):
        self.block = True
        old = find_channel(self.plan, "channel-a")
        started = self.service.begin_swap(
            _swap(self.plan, "channel-a", "first"),
            "test-key",
        )
        await asyncio.sleep(0)

        during = self.service.get_plan(self.plan.id)
        self.assertEqual(find_channel(during, "channel-a").current.id, old.current.id)
        self.assertEqual(during.revision, self.plan.revision)

        self.release.set()
        result = await self._result(started.id)
        changed = find_channel(result.plan, "channel-a")
        self.assertNotEqual(changed.current.id, old.current.id)
        self.assertEqual(changed.revision, old.revision + 1)
        self.assertEqual(result.plan.revision, self.plan.revision + 1)
        self.assertEqual(
            result.plan.totalKcal,
            sum(meal.totalKcal for meal in result.plan.meals),
        )

    async def test_busy_click_creates_no_second_job_and_does_not_queue(self):
        self.block = True
        started = self.service.begin_swap(
            _swap(self.plan, "channel-a", "busy"),
            "test-key",
        )
        await self.factory_started.wait()

        with self.assertRaises(AppError) as caught:
            self.service.begin_swap(
                _swap(self.plan, "channel-b", "blocked"),
                "test-key",
            )
        self.assertEqual(caught.exception.code, "REPLACEMENT_BUSY")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.service.active_swap_job_id, started.id)

        self.release.set()
        await self._result(started.id)

    async def test_exact_idempotent_replay_returns_same_job(self):
        self.block = True
        request = _swap(self.plan, "channel-a", "same")
        first = self.service.begin_swap(request, "test-key")
        replay = self.service.begin_swap(request, "test-key")
        self.assertEqual(first.id, replay.id)
        self.release.set()
        await self._result(first.id)

    async def test_failure_preserves_current_and_unlocks_for_retry(self):
        self.fail = True
        before = self.service.get_plan(self.plan.id)
        started = self.service.begin_swap(
            _swap(before, "channel-a", "failure"),
            "test-key",
        )
        await self.job_store.wait(started.id)
        envelope = self.job_store.get(started.id)

        self.assertEqual(envelope["status"], "failed")
        after = self.service.get_plan(self.plan.id)
        self.assertEqual(after, before)
        self.assertIsNone(self.service.active_swap_job_id)

        self.fail = False
        retry = self.service.begin_swap(
            _swap(after, "channel-a", "retry"),
            "test-key",
        )
        await self._result(retry.id)

    async def test_twenty_swaps_keep_the_original_fixed_budget(self):
        original_budget = tuple(
            find_channel(self.plan, "channel-a").ingredientBudget
        )
        plan = self.plan
        for index in range(20):
            started = self.service.begin_swap(
                _swap(plan, "channel-a", str(index)),
                "test-key",
            )
            plan = (await self._result(started.id)).plan

        self.assertEqual(
            tuple(find_channel(plan, "channel-a").ingredientBudget),
            original_budget,
        )
        self.assertEqual(
            [call[1] for call in self.calls],
            [
                tuple((item.id, item.estimatedGrams) for item in original_budget)
            ]
            * 20,
        )
