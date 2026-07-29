import unittest
from unittest.mock import AsyncMock, patch

from app import calories, channels
from app.jobs import AsyncJobStore
from app.models import (
    CalorieLine,
    FoodLineDraft,
    IngredientInput,
    Meal,
    MealPlan,
    MealPlanDraft,
    PlanConstraints,
    Recipe,
    RecipeChannel,
    RecipeDraft,
    RecipeStep,
)
from app.nutrition import NutritionMatch


def _calorie_line(name: str, kcal: int, estimated: bool = False) -> CalorieLine:
    return CalorieLine(
        name=name,
        nutritionQuery="tomatoes red ripe raw",
        nutritionFallbackQuery="tomatoes raw",
        grams=100,
        note="",
        estimatedKcalPer100g=kcal,
        kcalPer100g=kcal,
        kcal=kcal,
        estimated=estimated,
        nutritionSource="耄耋估算" if estimated else "USDA FoodData Central",
        sourceId=None if estimated else 1001,
        sourceDescription=name,
        sourceUrl=None if estimated else "https://example.test/1001",
    )


def _recipe(recipe_id: str, kcal: int, estimated: bool = False) -> Recipe:
    return Recipe(
        id=recipe_id,
        name=recipe_id,
        description="测试菜",
        ingredients=[_calorie_line(recipe_id, kcal, estimated)],
        seasonings=[],
        steps=[RecipeStep(title="烹饪", detail="完成烹饪。", minutes=10)],
        totalMinutes=10,
        difficulty="简单",
        lowCalorieReason="测试",
        tools=[],
        tags=[],
        totalKcal=kcal,
        perPersonKcal=round(kcal / 2),
        calorieEstimated=estimated,
    )


def _channel(channel_id: str, current: Recipe) -> RecipeChannel:
    return RecipeChannel(
        id=channel_id,
        revision=0,
        ingredientBudget=[
            {
                "id": channel_id,
                "name": "番茄",
                "amount": 1,
                "unit": "份",
                "estimatedGrams": 100,
            }
        ],
        current=current,
    )


def _plan(*items: RecipeChannel) -> MealPlan:
    return MealPlan(
        id="plan-test",
        revision=0,
        title="测试菜单",
        summary="测试",
        people=2,
        createdAt="2026-07-28T00:00:00+00:00",
        meals=[
            Meal(
                id="meal-test",
                label="午餐",
                channels=list(items),
                totalKcal=9999,
                perPersonKcal=9999,
            )
        ],
        totalKcal=9999,
        perPersonKcal=9999,
        tips=[],
        unusedIngredients=[],
        warnings=[],
        disclaimer="测试",
        agentTrace=[],
        skillVersions={},
    )


def _draft(name: str, estimate: float) -> RecipeDraft:
    return RecipeDraft(
        name=name,
        description="测试菜",
        ingredients=[
            FoodLineDraft(
                name="测试食材",
                nutritionQuery="rare ingredient raw",
                nutritionFallbackQuery="rare ingredient",
                grams=100,
                note="",
                estimatedKcalPer100g=estimate,
            )
        ],
        seasonings=[],
        steps=[RecipeStep(title="烹饪", detail="完成烹饪。", minutes=10)],
        totalMinutes=10,
        difficulty="简单",
        lowCalorieReason="测试",
        tools=[],
        tags=[],
    )


class RecipeChannelNutritionTest(unittest.IsolatedAsyncioTestCase):
    def test_visible_totals_include_root_and_only_current_recipes(self):
        plan = _plan(
            _channel("channel-a", _recipe("current-usda", 120)),
            _channel(
                "channel-b",
                _recipe("current-estimated", 180, estimated=True),
            ),
        )

        updated = calories.recompute_visible_nutrition(plan)

        self.assertEqual(updated.meals[0].totalKcal, 300)
        self.assertEqual(updated.totalKcal, 300)
        self.assertEqual(updated.perPersonKcal, 150)
        self.assertIn(calories.NUTRITION_ESTIMATE_WARNING, updated.warnings)

    async def test_calculate_recipe_draft_preserves_source_metadata(self):
        match = NutritionMatch(
            kcal_per_100g=73,
            source="耄耋估算",
            source_id=None,
            source_description="测试食材（USDA 未匹配）",
            source_url=None,
            estimated=True,
        )
        draft = _draft("新菜", 73)
        with patch.object(
            calories,
            "_resolve_matches",
            new=AsyncMock(
                return_value={
                    calories.nutrition_query_key(draft.ingredients[0]): match
                }
            ),
        ):
            recipe = await calories.calculate_recipe_draft(
                draft,
                people=2,
                recipe_id="recipe-swap",
            )

        self.assertTrue(recipe.calorieEstimated)
        self.assertEqual(recipe.ingredients[0].nutritionSource, "耄耋估算")

    async def test_channel_plan_calculates_only_current_recipes(self):
        current = _draft("当前菜", 61)
        draft = MealPlanDraft.model_validate(
            {
                "title": "测试菜单",
                "summary": "测试",
                "meals": [{"label": "午餐", "recipes": [current.model_dump()]}],
                "tips": [],
                "unusedIngredients": [],
            }
        )
        prepared = [
            [
                channels.InitialChannelDraft(
                    channel_id="channel-real-a",
                    ingredient_budget=(
                        IngredientInput(
                            id="tomato",
                            name="番茄",
                            amount=1,
                            unit="份",
                            estimatedGrams=100,
                        ),
                    ),
                    current=current,
                )
            ]
        ]
        calculated = [_recipe("recipe-current", 120)]

        with patch.object(
            calories,
            "calculate_drafts",
            new=AsyncMock(return_value=calculated),
        ) as calculate_batch:
            plan = await channels.calculate_channel_plan(
                draft=draft,
                channels=prepared,
                people=2,
            )

        calculate_batch.assert_awaited_once()
        self.assertEqual(
            [item.name for item in calculate_batch.await_args.args[0]],
            ["当前菜"],
        )
        self.assertEqual(plan.totalKcal, 120)

    async def test_default_swap_uses_real_channel_and_recipe_helper(self):
        service = channels.RecipeChannelService(AsyncJobStore())
        current = _recipe("recipe-current", 120)
        draft = _draft("新菜", 73)
        calculated = _recipe("recipe-swap", 73, estimated=True)
        budget = (
            IngredientInput(
                id="tomato",
                name="番茄",
                amount=1,
                unit="份",
                estimatedGrams=100,
            ),
        )
        constraints = PlanConstraints(
            people=2,
            mealCount=1,
            tools=[],
            avoid=[],
            flavor="清淡",
        )

        with (
            patch.object(
                channels,
                "generate_channel_swap_candidate",
                new=AsyncMock(return_value=draft),
            ) as generate,
            patch.object(
                calories,
                "calculate_recipe_draft",
                new=AsyncMock(return_value=calculated),
            ) as calculate,
        ):
            result = await service._default_swap_recipe(
                "channel-real-a",
                budget,
                current,
                constraints,
                "test-key",
            )

        self.assertEqual(result, calculated)
        self.assertEqual(
            generate.await_args.kwargs["channel_id"],
            "channel-real-a",
        )
        calculate.assert_awaited_once()
