import json
import unittest

from app.models import (
    MODEL_CONTRACT_VERSION,
    GeneratePlanRequest,
    IngredientInput,
    MealPlanDraft,
    PlanConstraints,
    RecipeDraft,
)
from app.prompts import (
    audit_snapshot,
    build_audit_messages,
    build_channel_audit_messages,
    build_channel_swap_messages,
    build_plan_messages,
)


def _target_channel_facts(prompt: str):
    return json.loads(
        prompt.split("# TARGET_CHANNEL_ONLY\n", 1)[1].split(
            "\n# FIXED_OUTPUT", 1
        )[0]
    )


def _draft() -> MealPlanDraft:
    return MealPlanDraft.model_validate(
        {
            "title": "番茄轻食",
            "summary": "一餐家常菜",
            "meals": [
                {
                    "label": "午餐",
                    "recipes": [
                        {
                            "name": "少油炒番茄",
                            "description": "酸甜清爽",
                            "ingredients": [
                                {
                                    "name": "番茄",
                                    "nutritionQuery": "tomatoes red ripe raw",
                                    "nutritionFallbackQuery": "tomatoes raw",
                                    "grams": 200,
                                    "note": "",
                                    "estimatedKcalPer100g": 18,
                                }
                            ],
                            "seasonings": [],
                            "steps": [
                                {
                                    "title": "炒制",
                                    "detail": "炒至出汁。",
                                    "minutes": 8,
                                }
                            ],
                            "totalMinutes": 10,
                            "difficulty": "简单",
                            "lowCalorieReason": "少油。",
                            "tools": ["炒锅"],
                            "tags": [],
                        }
                    ],
                }
            ],
            "tips": [],
            "unusedIngredients": [],
        }
    )


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


class PromptBudgetTest(unittest.TestCase):
    def test_plan_context_has_one_compact_contract(self):
        messages = build_plan_messages(_request())
        serialized = json.dumps(messages, ensure_ascii=False)
        self.assertEqual(serialized.count(MODEL_CONTRACT_VERSION), 1)
        self.assertNotIn("$defs", serialized)
        self.assertIn('"estimatedKcalPer100g"', messages[1]["content"])

    def test_plan_context_is_below_fixed_character_budget(self):
        serialized = json.dumps(build_plan_messages(_request()), ensure_ascii=False)
        self.assertLess(len(serialized), 6500)

    def test_channel_swap_context_only_contains_target_budget_and_current(self):
        current: RecipeDraft = _draft().meals[0].recipes[0]
        budget = tuple(_request().ingredients)
        initial_messages = build_channel_swap_messages(
            channel_id="channel-a",
            ingredient_budget=budget,
            current=current,
            constraints=PlanConstraints.model_validate(
                _request().model_dump(exclude={"ingredients"})
            ),
            violations=[],
            candidate=None,
        )
        repair_violation = "只修复这一个违规"
        repair_candidate = current.model_copy(
            update={"name": "番茄清汤", "tools": ["汤锅"]}
        )
        repair_messages = build_channel_swap_messages(
            channel_id="channel-a",
            ingredient_budget=budget,
            current=current,
            constraints=PlanConstraints.model_validate(
                _request().model_dump(exclude={"ingredients"})
            ),
            violations=[repair_violation],
            candidate=repair_candidate,
        )
        initial_facts = _target_channel_facts(initial_messages[1]["content"])
        repair_facts = _target_channel_facts(repair_messages[1]["content"])
        serialized = json.dumps(initial_messages, ensure_ascii=False)
        self.assertLess(len(serialized), 7000)
        self.assertNotIn("sourceDescription", serialized)
        self.assertNotIn("agentTrace", serialized)
        self.assertNotIn("unusedIngredients", serialized)
        self.assertIn('"ingredientBudget"', initial_messages[1]["content"])
        self.assertIn(current.name, serialized)
        self.assertNotIn('"backupStatus"', serialized)
        self.assertNotIn("candidateToRepair", initial_facts)
        self.assertNotIn("repairOnly", initial_facts)
        self.assertEqual(
            repair_facts["candidateToRepair"],
            repair_candidate.model_dump(mode="json"),
        )
        self.assertEqual(repair_facts["repairOnly"], [repair_violation])
        initial_instruction = initial_messages[1]["content"].split(
            "# TARGET_CHANNEL_ONLY", 1
        )[0]
        repair_instruction = repair_messages[1]["content"].split(
            "# TARGET_CHANNEL_ONLY", 1
        )[0]
        self.assertIn("现做一份不同做法的完整新菜", initial_instruction)
        self.assertNotIn("只修复", initial_instruction)
        self.assertIn(
            "只修复 candidateToRepair 中 repairOnly 列出的明确基础错误",
            repair_instruction,
        )

    def test_audit_snapshot_includes_auditable_facts_but_not_nutrition_contract(self):
        serialized = json.dumps(
            audit_snapshot(_draft(), _request()),
            ensure_ascii=False,
        )
        self.assertNotIn("nutritionQuery", serialized)
        self.assertIn("炒至出汁", serialized)
        self.assertIn('"inventory"', serialized)
        self.assertLess(len(serialized), 4500)

    def test_plan_audit_is_llm_skill_driven_without_python_verdict(self):
        serialized = json.dumps(
            build_audit_messages(_draft(), _request()),
            ensure_ascii=False,
        )
        self.assertIn("name: plan-audit", serialized)
        self.assertNotIn("PYTHON_VIOLATIONS", serialized)
        self.assertIn("有疑问一律通过", serialized)

    def test_channel_audit_uses_its_own_compact_llm_skill(self):
        current = _draft().meals[0].recipes[0]
        messages = build_channel_audit_messages(
            channel_id="channel-a",
            ingredient_budget=tuple(_request().ingredients),
            current=current,
            candidate=current.model_copy(update={"name": "番茄热拌"}),
            constraints=PlanConstraints.model_validate(
                _request().model_dump(exclude={"ingredients"})
            ),
        )
        serialized = json.dumps(messages, ensure_ascii=False)
        self.assertIn("name: recipe-channel-audit", serialized)
        self.assertIn("有疑问一律通过", serialized)
        self.assertIn("烹饪大类相同但菜名和做法明显不同", serialized)
        self.assertIn("质量建议、缺乏创意或偏好差异", serialized)
        self.assertIn("任何无法从输入事实证明的错误都必须通过", serialized)
        self.assertIn("只有上述列出的明确事实可写入 `violations`", serialized)
        self.assertLess(len(serialized), 7000)

    def test_channel_swap_skill_allows_same_cooking_category_for_distinct_prep(self):
        current = _draft().meals[0].recipes[0]
        messages = build_channel_swap_messages(
            channel_id="channel-a",
            ingredient_budget=tuple(_request().ingredients),
            current=current,
            constraints=PlanConstraints.model_validate(
                _request().model_dump(exclude={"ingredients"})
            ),
            candidate=current.model_copy(update={"name": "番茄热拌"}),
            violations=["明确使用了未提供的烤箱"],
        )
        serialized = json.dumps(messages, ensure_ascii=False)
        self.assertIn("做法需有可辨识差异，烹饪大类可以相同", serialized)
        self.assertIn("仅修复列出的硬错误", serialized)


if __name__ == "__main__":
    unittest.main()
