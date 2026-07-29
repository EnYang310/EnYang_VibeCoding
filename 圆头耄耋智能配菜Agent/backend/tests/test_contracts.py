import importlib
import importlib.util
import unittest

from pydantic import ValidationError

from app.models import (
    FoodLineDraft,
    MealPlanDraft,
    PlanAuditResult,
    RecognizeModelResult,
    RecipeDraft,
)


RESPONSE_MODELS = (
    RecognizeModelResult,
    MealPlanDraft,
    PlanAuditResult,
    RecipeDraft,
)

ALLOWED_WIRE_SCHEMA_KEYS = {
    "$defs",
    "$ref",
    "type",
    "properties",
    "required",
    "items",
    "additionalProperties",
    "enum",
    "anyOf",
}


def walk_schema_keywords(value, *, mapping_keys: bool = False):
    if isinstance(value, dict):
        for key, child in value.items():
            if not mapping_keys:
                yield key
            yield from walk_schema_keywords(
                child,
                mapping_keys=key in {"properties", "$defs"},
            )
    elif isinstance(value, list):
        for child in value:
            yield from walk_schema_keywords(child)


def valid_food_line_payload() -> dict:
    return {
        "name": "番茄",
        "nutritionQuery": "tomatoes, red, ripe, raw",
        "nutritionFallbackQuery": "tomatoes, raw",
        "grams": 100,
        "note": "",
        "estimatedKcalPer100g": 18,
    }


def valid_recipe_payload(name: str = "少油炒番茄") -> dict:
    return {
        "name": name,
        "description": "酸甜清爽的家常菜。",
        "ingredients": [valid_food_line_payload()],
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


def valid_meal_plan_draft_payload() -> dict:
    return {
        "title": "番茄轻食",
        "summary": "一餐家常菜。",
        "meals": [
            {
                "label": "午餐",
                "recipes": [valid_recipe_payload()],
            }
        ],
        "tips": [],
        "unusedIngredients": [],
    }


class FixedModelContractTest(unittest.TestCase):
    def test_four_kimi_outputs_have_exact_fixed_fields(self):
        expected = {
            RecognizeModelResult: {"ingredients", "warnings"},
            MealPlanDraft: {
                "title",
                "summary",
                "meals",
                "tips",
                "unusedIngredients",
            },
            PlanAuditResult: {"passed", "violations", "summary"},
            RecipeDraft: {
                "name",
                "description",
                "ingredients",
                "seasonings",
                "steps",
                "totalMinutes",
                "difficulty",
                "lowCalorieReason",
                "tools",
                "tags",
            },
        }

        for model, fields in expected.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(set(model.model_fields), fields)
                self.assertTrue(
                    all(field.is_required() for field in model.model_fields.values())
                )

    def test_four_kimi_outputs_reject_unknown_fields(self):
        payloads = {
            RecognizeModelResult: {"ingredients": [], "warnings": []},
            MealPlanDraft: valid_meal_plan_draft_payload(),
            PlanAuditResult: {
                "passed": True,
                "violations": [],
                "summary": "通过",
            },
            RecipeDraft: valid_recipe_payload(),
        }

        for model, payload in payloads.items():
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.model_validate({**payload, "legacyField": True})

    def test_recognition_requires_warnings_even_when_empty(self):
        with self.assertRaises(ValidationError):
            RecognizeModelResult.model_validate({"ingredients": []})

    def test_plan_requires_all_top_level_arrays(self):
        for missing in ("tips", "unusedIngredients"):
            payload = valid_meal_plan_draft_payload()
            payload.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                MealPlanDraft.model_validate(payload)

    def test_food_line_requires_note_and_estimate(self):
        for missing in ("note", "estimatedKcalPer100g"):
            payload = valid_food_line_payload()
            payload.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                FoodLineDraft.model_validate(payload)

    def test_model_outputs_reject_null_and_old_fields(self):
        with self.assertRaises(ValidationError):
            PlanAuditResult.model_validate(
                {
                    "passed": True,
                    "violations": None,
                    "summary": "通过",
                }
            )
        with self.assertRaises(ValidationError):
            PlanAuditResult.model_validate(
                {
                    "passed": True,
                    "violations": [],
                    "summary": "通过",
                    "reason": "旧字段",
                }
            )

    def test_old_plan_shape_is_never_accepted(self):
        with self.assertRaises(ValidationError):
            MealPlanDraft.model_validate(
                {
                    "meals": [{"mealIndex": 1, "dishes": []}],
                    "unusedIngredients": [],
                }
            )

    def test_difficulty_enum_is_fixed(self):
        payload = valid_recipe_payload()
        payload["difficulty"] = "困难"
        with self.assertRaises(ValidationError):
            RecipeDraft.model_validate(payload)


class WireContractTest(unittest.TestCase):
    def contracts_module(self):
        spec = importlib.util.find_spec("app.contracts")
        self.assertIsNotNone(spec, "app.contracts must exist")
        return importlib.import_module("app.contracts")

    def test_all_kimi_schemas_only_use_supported_keywords(self):
        contracts = self.contracts_module()
        for model in RESPONSE_MODELS:
            with self.subTest(model=model.__name__):
                wire = contracts.kimi_mfjs_schema(model)
                keys = set(walk_schema_keywords(wire))
                self.assertTrue(keys <= ALLOWED_WIRE_SCHEMA_KEYS, keys)

    def test_property_and_definition_names_are_preserved(self):
        contracts = self.contracts_module()
        wire = contracts.kimi_mfjs_schema(MealPlanDraft)

        self.assertIn("title", wire["properties"])
        self.assertIn("RecipeDraft", wire["$defs"])
        self.assertIn(
            "description",
            wire["$defs"]["RecipeDraft"]["properties"],
        )

    def test_required_contains_every_property_for_every_object(self):
        contracts = self.contracts_module()
        wire = contracts.kimi_mfjs_schema(MealPlanDraft)

        def assert_objects_are_closed_and_required(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertFalse(value["additionalProperties"])
                    self.assertEqual(
                        set(value["required"]),
                        set(value["properties"]),
                    )
                for child in value.values():
                    assert_objects_are_closed_and_required(child)
            elif isinstance(value, list):
                for child in value:
                    assert_objects_are_closed_and_required(child)

        assert_objects_are_closed_and_required(wire)

    def test_compact_skeleton_lists_the_complete_nested_shape(self):
        contracts = self.contracts_module()
        skeleton = contracts.compact_contract_skeleton(MealPlanDraft)

        for field in (
            "title",
            "summary",
            "meals",
            "tips",
            "unusedIngredients",
            "label",
            "recipes",
            "name",
            "description",
            "ingredients",
            "seasonings",
            "steps",
            "totalMinutes",
            "difficulty",
            "lowCalorieReason",
            "tools",
            "tags",
            "nutritionQuery",
            "nutritionFallbackQuery",
            "grams",
            "note",
            "estimatedKcalPer100g",
            "detail",
            "minutes",
        ):
            with self.subTest(field=field):
                self.assertIn(field, skeleton)
        self.assertNotIn("$defs", skeleton)
        self.assertNotIn("$ref", skeleton)
        self.assertLess(len(skeleton), 1800)

    def test_contract_version_is_exposed_with_skeleton(self):
        contracts = self.contracts_module()
        self.assertEqual(
            contracts.MODEL_CONTRACT_VERSION,
            "maodie-model-contract-1.7.0",
        )


if __name__ == "__main__":
    unittest.main()
