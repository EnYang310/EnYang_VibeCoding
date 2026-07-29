import importlib
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.kimi import AppError
from app.models import AsyncJobResponse, ChannelSwapResult, MealPlan
from backend.tests.test_recipe_channels import valid_meal_plan_payload


main = importlib.import_module("app.main")


def queued_swap_job(identifier: str = "job-swap") -> dict:
    return {
        "id": identifier,
        "kind": "channel_swap",
        "status": "queued",
        "phase": "queued",
        "message": "任务已创建。",
        "version": 0,
        "result": None,
        "error": None,
    }


class RecordingChannelService:
    def __init__(self):
        self.plan = MealPlan.model_validate(valid_meal_plan_payload())
        self.swap_requests = []
        self.jobs = {"job-swap": queued_swap_job()}

    def get_plan(self, plan_id):
        if plan_id != self.plan.id:
            raise AppError("PLAN_NOT_FOUND", "菜单不存在。", 404, True)
        return self.plan

    def begin_swap(self, request, api_key):
        self.swap_requests.append((request, api_key))
        return AsyncJobResponse[ChannelSwapResult].model_validate(
            queued_swap_job()
        )

    def get_swap_job(self, job_id):
        return self.jobs.get(job_id)


class ChannelApiTest(unittest.TestCase):
    def setUp(self):
        self.service = RecordingChannelService()
        self.client = TestClient(main.app)

    def test_plan_lookup_and_swap_delegate_to_service(self):
        body = {
            "planId": self.service.plan.id,
            "channelId": "channel-a",
            "planRevision": 0,
            "channelRevision": 0,
            "idempotencyKey": "swap-channel-a-0001",
        }
        with (
            patch.object(main, "channel_service", self.service),
            patch.object(main, "resolve_api_key", return_value="test-key"),
        ):
            fetched = self.client.get(f"/api/plans/{self.service.plan.id}")
            started = self.client.post("/api/plans/channel-swaps", json=body)

        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(started.status_code, 202, started.text)
        self.assertEqual(started.json()["kind"], "channel_swap")
        self.assertEqual(self.service.swap_requests[0][1], "test-key")

    def test_swap_job_lookup_and_removed_refill_routes(self):
        with patch.object(main, "channel_service", self.service):
            found = self.client.get(
                "/api/plans/channel-swap-jobs/job-swap"
            )
            missing = self.client.get(
                "/api/plans/channel-swap-jobs/missing"
            )
            removed = self.client.post("/api/plans/channel-refills", json={})

        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual(found.json()["kind"], "channel_swap")
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(
            missing.json()["error"]["code"],
            "CHANNEL_SWAP_JOB_NOT_FOUND",
        )
        self.assertEqual(removed.status_code, 405)

    def test_invalid_swap_has_explainable_error(self):
        response = self.client.post("/api/plans/channel-swaps", json={})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_health_exposes_release(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["appVersion"], "1.7.0")
