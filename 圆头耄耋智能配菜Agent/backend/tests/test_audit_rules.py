import unittest

from app.audit import (
    find_inventory_name,
    normalize_plan_inventory,
)
from app.models import GeneratePlanRequest, IngredientInput, MealPlanDraft, RecipeDraft


def _request(*, tools=None, avoid=None, grams=500) -> GeneratePlanRequest:
    return GeneratePlanRequest(
        ingredients=[
            IngredientInput(
                id="tomato",
                name="番茄",
                amount=3,
                unit="个",
                estimatedGrams=grams,
            )
        ],
        people=2,
        mealCount=1,
        tools=tools or ["炒锅"],
        avoid=avoid or [],
        flavor="清淡",
    )


def _line(name="番茄", grams=200) -> dict:
    return {
        "name": name,
        "nutritionQuery": "tomatoes red ripe raw",
        "nutritionFallbackQuery": "tomatoes raw",
        "grams": grams,
        "note": "",
        "estimatedKcalPer100g": 18,
    }


def _recipe(
    *,
    name="少油炒番茄",
    ingredients=None,
    seasonings=None,
    tools=None,
    detail="用炒锅翻炒至番茄出汁。",
) -> RecipeDraft:
    return RecipeDraft.model_validate(
        {
            "name": name,
            "description": "清爽家常菜。",
            "ingredients": ingredients or [_line()],
            "seasonings": seasonings or [],
            "steps": [{"title": "炒制", "detail": detail, "minutes": 8}],
            "totalMinutes": 10,
            "difficulty": "简单",
            "lowCalorieReason": "少油。",
            "tools": tools or ["炒锅"],
            "tags": ["家常"],
        }
    )


def _draft(recipes) -> MealPlanDraft:
    return MealPlanDraft(
        title="测试菜单",
        summary="测试",
        meals=[{"label": "午餐", "recipes": recipes}],
        tips=[],
        unusedIngredients=[],
    )


class DeterministicAuditRulesTest(unittest.TestCase):
    def test_inventory_normalization_never_creates_zero_gram_line(self):
        recipe = _recipe(ingredients=[_line(grams=200)])
        normalized = normalize_plan_inventory(_draft([recipe]), _request(grams=0.5))
        self.assertGreater(
            normalized.meals[0].recipes[0].ingredients[0].grams,
            0,
        )

    def test_inventory_name_matching_is_only_objective_bookkeeping(self):
        self.assertEqual(
            find_inventory_name("去皮鸡胸肉", ["鸡胸肉", "番茄"]),
            "鸡胸肉",
        )


if __name__ == "__main__":
    unittest.main()
