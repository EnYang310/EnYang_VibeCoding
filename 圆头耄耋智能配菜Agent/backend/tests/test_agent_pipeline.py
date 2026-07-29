import asyncio
import unittest
from unittest.mock import patch

from app import agent, channels
from app.kimi import AppError
from app.models import (
    GeneratePlanRequest,
    IngredientInput,
    MealPlan,
    MealPlanDraft,
)
from backend.tests.test_recipe_channels import valid_meal_plan_payload


def _request() -> GeneratePlanRequest:
    return GeneratePlanRequest(
        ingredients=[
            IngredientInput(
                id="tomato",
                name="番茄",
                amount=3,
                unit="个",
                estimatedGrams=500,
            )
        ],
        people=2,
        mealCount=1,
        tools=["炒锅", "汤锅"],
        avoid=[],
        flavor="清淡",
    )


def _draft(grams: float = 300) -> MealPlanDraft:
    return MealPlanDraft.model_validate(
        {
            "title": "番茄轻食",
            "summary": "一餐家常菜",
            "meals": [
                {
                    "label": "周六午餐",
                    "recipes": [
                        {
                            "name": "少油炒番茄",
                            "description": "酸甜清爽",
                            "ingredients": [
                                {
                                    "name": "番茄",
                                    "nutritionQuery": "tomatoes red ripe raw",
                                    "nutritionFallbackQuery": "tomatoes raw",
                                    "grams": grams,
                                    "note": "",
                                    "estimatedKcalPer100g": 18,
                                }
                            ],
                            "seasonings": [],
                            "steps": [
                                {
                                    "title": "炒制",
                                    "detail": "炒至番茄变软出汁。",
                                    "minutes": 8,
                                }
                            ],
                            "totalMinutes": 10,
                            "difficulty": "简单",
                            "lowCalorieReason": "少油且以蔬菜为主。",
                            "tools": ["炒锅"],
                            "tags": ["低卡"],
                        }
                    ],
                }
            ],
            "tips": [],
            "unusedIngredients": [],
        }
    )


def _calculated_plan() -> MealPlan:
    return MealPlan.model_validate(valid_meal_plan_payload())


def _initial_channel_fixture():
    base = _draft().meals[0].recipes[0]

    def recipe(name: str, ingredient: str, primary: str, fallback: str):
        line = base.ingredients[0].model_copy(
            update={
                "name": ingredient,
                "nutritionQuery": primary,
                "nutritionFallbackQuery": fallback,
                "grams": 80,
            }
        )
        return base.model_copy(
            update={
                "name": name,
                "ingredients": [line],
            }
        )

    recipes = [
        recipe("菜-A", "番茄", "tomatoes raw", "tomatoes red raw"),
        recipe("菜-B", "鸡蛋", "egg whole raw", "egg raw"),
        recipe("菜-C", "牛肉", "beef raw", "beef lean raw"),
    ]
    draft = MealPlanDraft.model_validate(
        {
            "title": "并行备选测试",
            "summary": "验证初始通道顺序与失败清理。",
            "meals": [
                {
                    "label": "午餐",
                    "recipes": [
                        recipes[0].model_dump(),
                        recipes[1].model_dump(),
                    ],
                },
                {
                    "label": "晚餐",
                    "recipes": [recipes[2].model_dump()],
                },
            ],
            "tips": [],
            "unusedIngredients": [],
        }
    )
    source = GeneratePlanRequest(
        ingredients=[
            IngredientInput(
                id="tomato",
                name="番茄",
                amount=1,
                unit="份",
                estimatedGrams=100,
            ),
            IngredientInput(
                id="egg",
                name="鸡蛋",
                amount=1,
                unit="份",
                estimatedGrams=100,
            ),
            IngredientInput(
                id="beef",
                name="牛肉",
                amount=1,
                unit="份",
                estimatedGrams=100,
            ),
        ],
        people=2,
        mealCount=2,
        tools=["炒锅", "汤锅"],
        avoid=[],
        flavor="清淡",
    )
    return draft, source


def _message(payload) -> dict:
    return {"role": "assistant", "content": payload.model_dump_json()}


class PlanPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_initial_channels_keep_layout_without_generating_backups(self):
        draft, source = _initial_channel_fixture()
        result = await channels.build_initial_channel_drafts(
            draft=draft,
            source=source,
        )

        self.assertEqual(
            [[item.current.name for item in meal] for meal in result],
            [["菜-A", "菜-B"], ["菜-C"]],
        )
        self.assertTrue(
            all(
                not hasattr(item, "backup")
                for meal in result
                for item in meal
            )
        )

    async def test_normal_plan_uses_one_generation_and_one_advisory_audit(self):
        calls = []

        async def fake_chat(*args, **kwargs):
            calls.append(kwargs["schema_name"])
            if kwargs["schema_name"] == "meal_plan":
                return _message(_draft())
            return {
                "role": "assistant",
                "content": (
                    '{"passed":true,"violations":[],"summary":"基础合格"}'
                ),
            }

        async def fake_build(**kwargs):
            return [["prepared-channel"]]

        async def fake_calculate(**kwargs):
            return _calculated_plan()

        with (
            patch.object(agent, "chat_completion", fake_chat),
            patch.object(agent, "build_initial_channel_drafts", fake_build),
            patch.object(agent, "calculate_channel_plan", fake_calculate),
        ):
            result = await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(result.id, "plan-test")
        self.assertEqual(calls, ["meal_plan", "plan_audit"])

    async def test_channel_delivery_overlaps_advisory_audit(self):
        delivery_started = asyncio.Event()

        async def fake_chat(*args, **kwargs):
            if kwargs["schema_name"] == "meal_plan":
                return _message(_draft())
            await asyncio.wait_for(delivery_started.wait(), timeout=0.2)
            return {
                "role": "assistant",
                "content": (
                    '{"passed":true,"violations":[],"summary":"基础合格"}'
                ),
            }

        async def fake_build(**kwargs):
            delivery_started.set()
            await asyncio.sleep(0)
            return [["prepared-channel"]]

        async def fake_calculate(**kwargs):
            return _calculated_plan()

        with (
            patch.object(agent, "chat_completion", fake_chat),
            patch.object(agent, "build_initial_channel_drafts", fake_build),
            patch.object(agent, "calculate_channel_plan", fake_calculate),
        ):
            result = await asyncio.wait_for(
                agent.run_plan_pipeline(_request(), "test-key"),
                timeout=0.5,
            )

        self.assertEqual(result.id, "plan-test")

    async def test_inventory_overuse_is_normalized_without_repair(self):
        calls = []
        normalized_grams = []

        async def fake_chat(*args, **kwargs):
            calls.append(kwargs["schema_name"])
            if kwargs["schema_name"] == "meal_plan":
                return _message(_draft(600))
            return {
                "role": "assistant",
                "content": (
                    '{"passed":true,"violations":[],"summary":"基础合格"}'
                ),
            }

        async def fake_build(**kwargs):
            normalized_grams.append(
                kwargs["draft"].meals[0].recipes[0].ingredients[0].grams
            )
            return [["prepared-channel"]]

        async def fake_calculate(**kwargs):
            return _calculated_plan()

        with (
            patch.object(agent, "chat_completion", fake_chat),
            patch.object(agent, "build_initial_channel_drafts", fake_build),
            patch.object(agent, "calculate_channel_plan", fake_calculate),
        ):
            await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(normalized_grams, [500])
        self.assertEqual(calls, ["meal_plan", "plan_audit"])


if __name__ == "__main__":
    unittest.main()
