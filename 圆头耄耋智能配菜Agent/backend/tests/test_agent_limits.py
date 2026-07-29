import asyncio
import unittest
from unittest.mock import patch

from app import agent
from app.kimi import AppError
from app.models import PlanAuditResult
from backend.tests.test_agent_pipeline import _calculated_plan, _draft, _request


class BoundedPlanAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_llm_rejection_stops_after_two_repairs(self):
        generated = _draft()
        repair_calls = 0
        delivery_calls = 0
        audit_calls = 0

        async def fake_generate(*args, **kwargs):
            return generated

        async def fake_repair(*args, **kwargs):
            nonlocal repair_calls
            repair_calls += 1
            return generated

        async def fake_delivery(*args, **kwargs):
            nonlocal delivery_calls
            delivery_calls += 1
            return _calculated_plan()

        async def fake_audit(*args, **kwargs):
            nonlocal audit_calls
            audit_calls += 1
            return PlanAuditResult(
                passed=False,
                violations=["明确基础错误"],
                summary="不合格",
            )

        with (
            patch.object(agent, "_generate_plan_draft", fake_generate),
            patch.object(agent, "_repair_plan", fake_repair),
            patch.object(agent, "_build_delivery_plan", fake_delivery),
            patch.object(agent, "_run_llm_audit", fake_audit),
        ):
            with self.assertRaises(AppError) as caught:
                await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(caught.exception.code, "PLAN_AUDIT_FAILED")
        self.assertEqual(repair_calls, 2)
        self.assertEqual(delivery_calls, 3)
        self.assertEqual(audit_calls, 3)

    async def test_second_repair_can_pass_then_runs_checks_once(self):
        audit_results = [
            PlanAuditResult(
                passed=False,
                violations=["错误一"],
                summary="不合格",
            ),
            PlanAuditResult(
                passed=False,
                violations=["错误二"],
                summary="不合格",
            ),
            PlanAuditResult(
                passed=True,
                violations=[],
                summary="通过",
            ),
        ]
        repair_calls = 0
        delivery_calls = 0
        audit_calls = 0

        async def fake_generate(*args, **kwargs):
            return _draft()

        async def fake_repair(*args, **kwargs):
            nonlocal repair_calls
            repair_calls += 1
            return _draft()

        async def fake_delivery(*args, **kwargs):
            nonlocal delivery_calls
            delivery_calls += 1
            return _calculated_plan()

        async def fake_audit(*args, **kwargs):
            nonlocal audit_calls
            result = audit_results[audit_calls]
            audit_calls += 1
            return result

        with (
            patch.object(agent, "_generate_plan_draft", fake_generate),
            patch.object(agent, "_repair_plan", fake_repair),
            patch.object(agent, "_build_delivery_plan", fake_delivery),
            patch.object(agent, "_run_llm_audit", fake_audit),
        ):
            result = await agent.run_plan_pipeline(_request(), "test-key")

        self.assertEqual(result.id, "plan-test")
        self.assertEqual(repair_calls, 2)
        self.assertEqual(delivery_calls, 3)
        self.assertEqual(audit_calls, 3)

    async def test_llm_audit_transport_failure_is_not_forged_as_pass(self):
        async def fake_audit(*args, **kwargs):
            raise AppError("AI_TIMEOUT", "超时", 504, True)

        with (
            patch.object(
                agent,
                "_generate_plan_draft",
                return_value=_draft(),
            ),
            patch.object(agent, "_run_llm_audit", fake_audit),
            patch.object(
                agent,
                "_build_delivery_plan",
                return_value=_calculated_plan(),
            ),
        ):
            with self.assertRaises(AppError) as caught:
                await agent.run_plan_pipeline(_request(), "test-key")
        self.assertEqual(caught.exception.code, "AI_TIMEOUT")

    async def test_delivery_and_llm_audit_start_in_parallel(self):
        delivery_started = asyncio.Event()
        audit_started = asyncio.Event()

        async def fake_generate(*args, **kwargs):
            return _draft()

        async def fake_delivery(*args, **kwargs):
            delivery_started.set()
            await asyncio.wait_for(audit_started.wait(), timeout=0.2)
            return _calculated_plan()

        async def fake_audit(*args, **kwargs):
            audit_started.set()
            await asyncio.wait_for(delivery_started.wait(), timeout=0.2)
            return PlanAuditResult(
                passed=True,
                violations=[],
                summary="通过",
            )

        with (
            patch.object(agent, "_generate_plan_draft", fake_generate),
            patch.object(agent, "_build_delivery_plan", fake_delivery),
            patch.object(agent, "_run_llm_audit", fake_audit),
        ):
            result = await agent.run_plan_pipeline(_request(), "test-key")
        self.assertEqual(result.id, "plan-test")


if __name__ == "__main__":
    unittest.main()
