import unittest

from pydantic import ValidationError

from app import models


def valid_ingredient_payload(
    identifier: str = "tomato",
    name: str = "番茄",
) -> dict:
    return {
        "id": identifier,
        "name": name,
        "amount": 3,
        "unit": "个",
        "estimatedGrams": 500,
    }


def valid_calorie_line_payload() -> dict:
    return {
        "name": "番茄",
        "nutritionQuery": "tomatoes, red, ripe, raw",
        "nutritionFallbackQuery": "tomatoes, raw",
        "grams": 100,
        "note": "",
        "estimatedKcalPer100g": 18,
        "kcalPer100g": 18,
        "kcal": 18,
        "estimated": False,
        "nutritionSource": "USDA FoodData Central",
        "sourceId": 1,
        "sourceDescription": "Tomatoes, red, ripe, raw",
        "sourceUrl": "https://example.test/food/1",
    }


def valid_recipe_payload(identifier: str, name: str) -> dict:
    return {
        "id": identifier,
        "name": name,
        "description": "酸甜清爽的家常菜。",
        "ingredients": [valid_calorie_line_payload()],
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
        "totalKcal": 18,
        "perPersonKcal": 9,
        "calorieEstimated": False,
    }


def valid_recipe_channel_payload(identifier: str = "channel-a") -> dict:
    return {
        "id": identifier,
        "revision": 0,
        "ingredientBudget": [valid_ingredient_payload()],
        "current": valid_recipe_payload("recipe-current", "少油炒番茄"),
    }


def valid_meal_plan_payload() -> dict:
    return {
        "id": "plan-test",
        "revision": 0,
        "source": "kimi",
        "title": "番茄轻食",
        "summary": "一餐家常菜。",
        "people": 2,
        "createdAt": "2026-07-28T00:00:00+00:00",
        "meals": [
            {
                "id": "meal-test",
                "label": "午餐",
                "channels": [valid_recipe_channel_payload()],
                "totalKcal": 18,
                "perPersonKcal": 9,
            }
        ],
        "totalKcal": 18,
        "perPersonKcal": 9,
        "tips": [],
        "unusedIngredients": [],
        "warnings": [],
        "disclaimer": "测试",
        "agentTrace": [],
        "skillVersions": {},
    }


class RecipeChannelContractTest(unittest.TestCase):
    def test_channel_has_only_current_and_immutable_budget(self):
        channel = models.RecipeChannel.model_validate(
            valid_recipe_channel_payload()
        )

        self.assertIsInstance(channel.ingredientBudget, tuple)
        self.assertEqual(
            set(channel.model_dump()),
            {"id", "revision", "ingredientBudget", "current"},
        )

    def test_channel_rejects_removed_backup_fields(self):
        for field, value in (
            ("backup", valid_recipe_payload("backup", "备用菜")),
            ("backupStatus", "ready"),
            ("backupError", None),
        ):
            payload = {**valid_recipe_channel_payload(), field: value}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                models.RecipeChannel.model_validate(payload)

    def test_budget_requires_unique_ids_and_names(self):
        for field, value in (("id", " TOMATO "), ("name", " 番 茄 ")):
            payload = valid_recipe_channel_payload()
            duplicate = valid_ingredient_payload("egg", "鸡蛋")
            duplicate[field] = value
            payload["ingredientBudget"].append(duplicate)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                models.RecipeChannel.model_validate(payload)

    def test_plan_requires_root_totals_and_unique_ids(self):
        plan = models.MealPlan.model_validate(valid_meal_plan_payload())
        self.assertEqual(plan.totalKcal, 18)
        self.assertEqual(plan.perPersonKcal, 9)

        payload = valid_meal_plan_payload()
        payload.pop("totalKcal")
        with self.assertRaises(ValidationError):
            models.MealPlan.model_validate(payload)

        payload = valid_meal_plan_payload()
        duplicate = valid_recipe_channel_payload("channel-a")
        duplicate["current"]["id"] = "recipe-other"
        payload["meals"][0]["channels"].append(duplicate)
        with self.assertRaises(ValidationError):
            models.MealPlan.model_validate(payload)

    def test_swap_result_references_existing_channel(self):
        result = models.ChannelSwapResult.model_validate(
            {
                "plan": valid_meal_plan_payload(),
                "channelId": "channel-a",
            }
        )
        self.assertEqual(result.channelId, "channel-a")

        with self.assertRaises(ValidationError):
            models.ChannelSwapResult.model_validate(
                {
                    "plan": valid_meal_plan_payload(),
                    "channelId": "missing",
                }
            )
