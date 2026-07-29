import json
import unittest
from unittest.mock import AsyncMock, patch

from app import agent, channels
from app.kimi import AppError
from app.models import (
    PlanAuditResult,
    PlanConstraints,
    RecipeDraft,
    RecipeStep,
)
from backend.tests.test_agent_pipeline import (
    _calculated_plan,
    _draft,
    _message,
    _request,
)


def _prompt_facts(prompt: str, heading: str, next_heading: str):
    return json.loads(
        prompt.split(heading + "\n", 1)[1].split("\n" + next_heading, 1)[0]
    )


def _target_channel_facts(prompt: str):
    return _prompt_facts(prompt, "# TARGET_CHANNEL_ONLY", "# FIXED_OUTPUT")


def _channel_audit_facts(prompt: str):
    return _prompt_facts(prompt, "# CHANNEL_FACTS", "# RULES")


def _audited_candidate_facts(candidate: RecipeDraft):
    return {
        "name": candidate.name,
        "ingredients": [
            {"name": line.name, "grams": line.grams}
            for line in candidate.ingredients
        ],
        "seasonings": [
            {"name": line.name, "grams": line.grams}
            for line in candidate.seasonings
        ],
        "tools": candidate.tools,
        "steps": [
            "{}：{}".format(step.title, step.detail)
            for step in candidate.steps
        ],
    }


class LlmOnlyPlanAuditTest(unittest.IsolatedAsyncioTestCase):
    async def test_llm_rejection_repairs_then_reaudits_before_delivery(self):
        audits = [
            PlanAuditResult(
                passed=False,
                violations=["明确使用了未提供的烤箱"],
                summary="存在一项基础错误",
            ),
            PlanAuditResult(
                passed=True,
                violations=[],
                summary="基础要素合格",
            ),
        ]

        with (
            patch.object(
                agent,
                "_generate_plan_draft",
                new=AsyncMock(return_value=_draft()),
            ),
            patch.object(
                agent,
                "_run_llm_audit",
                new=AsyncMock(side_effect=audits),
            ) as llm_audit,
            patch.object(
                agent,
                "_repair_plan",
                new=AsyncMock(return_value=_draft()),
            ) as repair,
            patch.object(
                agent,
                "_build_delivery_plan",
                new=AsyncMock(return_value=_calculated_plan()),
            ) as delivery,
        ):
            result = await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(result.id, "plan-test")
        self.assertEqual(llm_audit.await_count, 2)
        repair.assert_awaited_once()
        self.assertEqual(delivery.await_count, 2)

    async def test_llm_rejection_stops_after_two_targeted_repairs(self):
        rejected = PlanAuditResult(
            passed=False,
            violations=["明确的基础错误"],
            summary="不合格",
        )
        with (
            patch.object(
                agent,
                "_generate_plan_draft",
                new=AsyncMock(return_value=_draft()),
            ),
            patch.object(
                agent,
                "_run_llm_audit",
                new=AsyncMock(return_value=rejected),
            ) as llm_audit,
            patch.object(
                agent,
                "_repair_plan",
                new=AsyncMock(return_value=_draft()),
            ) as repair,
            patch.object(
                agent,
                "_build_delivery_plan",
                new=AsyncMock(return_value=_calculated_plan()),
            ) as delivery,
        ):
            with self.assertRaises(AppError) as caught:
                await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(caught.exception.code, "PLAN_AUDIT_FAILED")
        self.assertEqual(llm_audit.await_count, 3)
        self.assertEqual(repair.await_count, 2)
        self.assertEqual(delivery.await_count, 3)


class LlmOnlyChannelAuditTest(unittest.IsolatedAsyncioTestCase):
    def _candidate(self, name: str, detail: str) -> RecipeDraft:
        current = _draft().meals[0].recipes[0]
        return current.model_copy(
            update={
                "name": name,
                "steps": [
                    RecipeStep(
                        title="煮制",
                        detail=detail,
                        minutes=8,
                    )
                ],
                "tools": ["汤锅"],
            }
        )

    async def test_channel_swap_reworks_candidate_twice_then_returns_third_audited_candidate(
        self,
    ):
        current = _draft().meals[0].recipes[0]
        candidates = [
            self._candidate("清煮番茄", "用汤锅煮至番茄变软。"),
            self._candidate("番茄蒸蛋", "隔水蒸至蛋液凝固。"),
            self._candidate("番茄菌菇汤", "煮至菌菇熟透即可。"),
        ]
        recipe_responses = iter(candidates)
        audits = [
            PlanAuditResult(
                passed=False,
                violations=["违规 1：新增预算外主要食材鸡胸肉"],
                summary="第一轮不合格",
            ),
            PlanAuditResult(
                passed=False,
                violations=["违规 2：明确使用了未提供的烤箱"],
                summary="第二轮不合格",
            ),
            PlanAuditResult(passed=True, violations=[], summary="合格"),
        ]
        recipe_messages = []
        audit_messages = []
        calls = []

        async def fake_chat(*args, **kwargs):
            schema_name = kwargs["schema_name"]
            user_prompt = args[1][1]["content"]
            calls.append(schema_name)
            if schema_name == "channel_swap_recipe":
                recipe_messages.append(user_prompt)
                return _message(next(recipe_responses))
            self.assertEqual(schema_name, "channel_swap_audit")
            audit_messages.append(user_prompt)
            return _message(audits.pop(0))

        with patch.object(channels, "chat_completion", fake_chat):
            result = await channels.generate_channel_swap_candidate(
                api_key="test-key",
                channel_id="channel-a",
                ingredient_budget=tuple(_request().ingredients),
                current=current,
                constraints=PlanConstraints.model_validate(
                    _request().model_dump(exclude={"ingredients"})
                ),
            )

        self.assertEqual(result, candidates[2])
        self.assertEqual(
            calls,
            [
                "channel_swap_recipe",
                "channel_swap_audit",
                "channel_swap_recipe",
                "channel_swap_audit",
                "channel_swap_recipe",
                "channel_swap_audit",
            ],
        )
        initial_facts = _target_channel_facts(recipe_messages[0])
        repair_one_facts = _target_channel_facts(recipe_messages[1])
        repair_two_facts = _target_channel_facts(recipe_messages[2])
        self.assertNotIn("candidateToRepair", initial_facts)
        self.assertNotIn("repairOnly", initial_facts)
        self.assertEqual(
            repair_one_facts["candidateToRepair"],
            candidates[0].model_dump(mode="json"),
        )
        self.assertEqual(
            repair_one_facts["repairOnly"],
            ["违规 1：新增预算外主要食材鸡胸肉"],
        )
        self.assertEqual(
            repair_two_facts["candidateToRepair"],
            candidates[1].model_dump(mode="json"),
        )
        self.assertEqual(
            repair_two_facts["repairOnly"],
            ["违规 2：明确使用了未提供的烤箱"],
        )
        initial_instruction = recipe_messages[0].split(
            "# TARGET_CHANNEL_ONLY", 1
        )[0]
        repair_instruction = recipe_messages[1].split(
            "# TARGET_CHANNEL_ONLY", 1
        )[0]
        self.assertIn("现做一份不同做法的完整新菜", initial_instruction)
        self.assertNotIn("只修复", initial_instruction)
        self.assertIn(
            "只修复 candidateToRepair 中 repairOnly 列出的明确基础错误",
            repair_instruction,
        )

        audit_facts = [_channel_audit_facts(prompt) for prompt in audit_messages]
        self.assertEqual(
            [facts["candidate"] for facts in audit_facts],
            [_audited_candidate_facts(candidate) for candidate in candidates],
        )

    async def test_channel_swap_fails_after_three_rejected_audits(self):
        current = _draft().meals[0].recipes[0]
        candidates = [
            self._candidate("清煮番茄", "用汤锅煮至番茄变软。"),
            self._candidate("番茄蒸蛋", "隔水蒸至蛋液凝固。"),
            self._candidate("番茄菌菇汤", "煮至菌菇熟透即可。"),
        ]
        recipe_responses = iter(candidates)
        rejected = PlanAuditResult(
            passed=False,
            violations=["明确基础错误"],
            summary="不合格",
        )
        calls = []

        async def fake_chat(*args, **kwargs):
            schema_name = kwargs["schema_name"]
            calls.append(schema_name)
            if schema_name == "channel_swap_recipe":
                return _message(next(recipe_responses))
            self.assertEqual(schema_name, "channel_swap_audit")
            return _message(rejected)

        with patch.object(channels, "chat_completion", fake_chat):
            with self.assertRaises(AppError) as caught:
                await channels.generate_channel_swap_candidate(
                    api_key="test-key",
                    channel_id="channel-a",
                    ingredient_budget=tuple(_request().ingredients),
                    current=current,
                    constraints=PlanConstraints.model_validate(
                        _request().model_dump(exclude={"ingredients"})
                    ),
                )

        self.assertEqual(caught.exception.code, "CHANNEL_SWAP_AUDIT_FAILED")
        self.assertEqual(calls.count("channel_swap_recipe"), 3)
        self.assertEqual(calls.count("channel_swap_audit"), 3)

    async def test_channel_swap_returns_after_first_clean_audit(self):
        current = _draft().meals[0].recipes[0]
        candidate = self._candidate("番茄菌菇汤", "煮至菌菇熟透即可。")
        calls = []

        async def fake_chat(*args, **kwargs):
            schema_name = kwargs["schema_name"]
            calls.append(schema_name)
            if schema_name == "channel_swap_recipe":
                return _message(candidate)
            self.assertEqual(schema_name, "channel_swap_audit")
            return _message(
                PlanAuditResult(passed=True, violations=[], summary="合格")
            )

        with patch.object(channels, "chat_completion", fake_chat):
            result = await channels.generate_channel_swap_candidate(
                api_key="test-key",
                channel_id="channel-a",
                ingredient_budget=tuple(_request().ingredients),
                current=current,
                constraints=PlanConstraints.model_validate(
                    _request().model_dump(exclude={"ingredients"})
                ),
            )

        self.assertEqual(result, candidate)
        self.assertEqual(calls.count("channel_swap_recipe"), 1)
        self.assertEqual(calls.count("channel_swap_audit"), 1)

    async def test_channel_swap_rejects_blank_audit_feedback_without_repair(self):
        current = _draft().meals[0].recipes[0]
        candidate = self._candidate("番茄菌菇汤", "煮至菌菇熟透即可。")
        calls = []

        async def fake_chat(*args, **kwargs):
            schema_name = kwargs["schema_name"]
            calls.append(schema_name)
            if schema_name == "channel_swap_recipe":
                return _message(candidate)
            self.assertEqual(schema_name, "channel_swap_audit")
            return _message(
                PlanAuditResult(
                    passed=False,
                    violations=["  ", "\t"],
                    summary=" \n ",
                )
            )

        with patch.object(channels, "chat_completion", fake_chat):
            with self.assertRaises(AppError) as caught:
                await channels.generate_channel_swap_candidate(
                    api_key="test-key",
                    channel_id="channel-a",
                    ingredient_budget=tuple(_request().ingredients),
                    current=current,
                    constraints=PlanConstraints.model_validate(
                        _request().model_dump(exclude={"ingredients"})
                    ),
                )

        self.assertEqual(caught.exception.code, "CHANNEL_SWAP_AUDIT_INVALID")
        self.assertEqual(calls.count("channel_swap_recipe"), 1)
        self.assertEqual(calls.count("channel_swap_audit"), 1)


if __name__ == "__main__":
    unittest.main()
