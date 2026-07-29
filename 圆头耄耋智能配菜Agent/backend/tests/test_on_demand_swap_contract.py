import unittest

from app import models
from backend.tests.test_recipe_channels import valid_meal_plan_payload


def on_demand_plan_payload() -> dict:
    return valid_meal_plan_payload()


class OnDemandSwapContractTest(unittest.TestCase):
    def test_channel_only_exposes_fixed_budget_and_current_recipe(self):
        plan = models.MealPlan.model_validate(on_demand_plan_payload())
        channel = plan.meals[0].channels[0]

        self.assertEqual(
            set(channel.model_dump()),
            {"id", "revision", "ingredientBudget", "current"},
        )
        self.assertIsInstance(channel.ingredientBudget, tuple)

    def test_plan_wire_contract_includes_root_calorie_totals(self):
        plan = models.MealPlan.model_validate(on_demand_plan_payload())

        self.assertEqual(plan.totalKcal, 18)
        self.assertEqual(plan.perPersonKcal, 9)

    def test_swap_job_uses_the_on_demand_kind_and_result(self):
        result_model = getattr(models, "ChannelSwapResult")
        result = result_model.model_validate(
            {
                "plan": on_demand_plan_payload(),
                "channelId": "channel-a",
            }
        )
        job = models.AsyncJobResponse[result_model].model_validate(
            {
                "id": "job-swap",
                "kind": "channel_swap",
                "status": "completed",
                "phase": "completed",
                "message": "换菜完成",
                "version": 2,
                "result": result.model_dump(),
                "error": None,
            }
        )

        self.assertEqual(job.kind, "channel_swap")
        self.assertEqual(job.result.channelId, "channel-a")

    def test_refill_models_are_removed(self):
        for name in (
            "ChannelRefillRequest",
            "ChannelRefillResult",
            "ChannelRefillAccepted",
            "ChannelSwapAccepted",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(models, name))
