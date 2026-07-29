import unittest

from pydantic import ValidationError

from app import models
from backend.tests.test_contracts import valid_food_line_payload
from backend.tests.test_recipe_channels import (
    valid_ingredient_payload,
    valid_meal_plan_payload,
)


def valid_generate_request_payload() -> dict:
    return {
        "ingredients": [
            valid_ingredient_payload("tomato", "番茄"),
            valid_ingredient_payload("egg", "鸡蛋"),
        ],
        "people": 2,
        "mealCount": 1,
        "tools": ["炒锅"],
        "avoid": [],
        "flavor": "清淡",
    }


def valid_channel_swap_payload() -> dict:
    return {
        "planId": "plan-test",
        "channelId": "channel-a",
        "planRevision": 0,
        "channelRevision": 0,
        "idempotencyKey": "swap-request-0001",
    }


class InputValidationTest(unittest.TestCase):
    def require_model(self, name: str):
        model = getattr(models, name, None)
        self.assertIsNotNone(model, f"{name} must exist")
        return model

    def test_rejects_chinese_primary_query(self):
        payload = valid_food_line_payload()
        payload["nutritionQuery"] = "番茄 生"
        with self.assertRaises(ValidationError):
            models.FoodLineDraft.model_validate(payload)

    def test_rejects_chinese_fallback_query(self):
        payload = valid_food_line_payload()
        payload["nutritionFallbackQuery"] = "番茄"
        with self.assertRaises(ValidationError):
            models.FoodLineDraft.model_validate(payload)

    def test_accepts_usda_punctuation_and_normalizes_whitespace(self):
        payload = valid_food_line_payload()
        payload["nutritionQuery"] = (
            "  chicken,  broilers or fryers, breast, meat only, raw  "
        )
        line = models.FoodLineDraft.model_validate(payload)
        self.assertEqual(
            line.nutritionQuery,
            "chicken, broilers or fryers, breast, meat only, raw",
        )

    def test_primary_and_fallback_queries_must_differ_after_normalization(self):
        payload = valid_food_line_payload()
        payload["nutritionQuery"] = " tomatoes,   raw "
        payload["nutritionFallbackQuery"] = "tomatoes, raw"

        with self.assertRaises(ValidationError):
            models.FoodLineDraft.model_validate(payload)

    def test_generate_request_rejects_duplicate_ids(self):
        body = valid_generate_request_payload()
        body["ingredients"][1]["id"] = " TOMATO "
        with self.assertRaises(ValidationError):
            models.GeneratePlanRequest.model_validate(body)

    def test_generate_request_rejects_normalized_duplicate_names(self):
        body = valid_generate_request_payload()
        body["ingredients"][1]["name"] = " 番 茄 "
        with self.assertRaises(ValidationError):
            models.GeneratePlanRequest.model_validate(body)

    def test_constraints_reject_normalized_duplicate_tools_and_avoid_items(self):
        for field, values in (
            ("tools", ["炒锅", " 炒 锅 "]),
            ("avoid", ["花生", " 花 生 "]),
        ):
            body = valid_generate_request_payload()
            body[field] = values
            with self.subTest(field=field), self.assertRaises(ValidationError):
                models.GeneratePlanRequest.model_validate(body)

    def test_channel_commands_require_idempotency_key(self):
        payload = valid_channel_swap_payload()
        payload.pop("idempotencyKey")
        with self.assertRaises(ValidationError):
            models.ChannelSwapRequest.model_validate(payload)

    def test_channel_commands_require_plan_and_channel_revisions(self):
        for field in ("planRevision", "channelRevision"):
            payload = valid_channel_swap_payload()
            payload.pop(field)
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                models.ChannelSwapRequest.model_validate(payload)

            payload = valid_channel_swap_payload()
            payload[field] = -1
            with self.subTest(negative=field), self.assertRaises(ValidationError):
                models.ChannelSwapRequest.model_validate(payload)

    def test_channel_commands_reject_embedded_recipe_plan_or_constraints(self):
        body = valid_channel_swap_payload()
        body.update(
            {
                "plan": valid_meal_plan_payload(),
                "recipeId": "legacy",
                "constraints": {
                    "people": 2,
                    "mealCount": 1,
                    "tools": [],
                    "avoid": [],
                    "flavor": "清淡",
                },
            }
        )
        with self.assertRaises(ValidationError):
            models.ChannelSwapRequest.model_validate(body)

    def test_channel_command_idempotency_key_has_bounded_length(self):
        for value in ("short", "x" * 129):
            payload = valid_channel_swap_payload()
            payload["idempotencyKey"] = value
            with self.subTest(length=len(value)), self.assertRaises(
                ValidationError
            ):
                models.ChannelSwapRequest.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
