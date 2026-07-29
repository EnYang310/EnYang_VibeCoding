import os
import unittest
from unittest.mock import patch

from app import contracts, kimi
from app.models import MealPlanDraft
from backend.tests.test_contracts import valid_meal_plan_draft_payload


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


def walk_schema_keywords(value, *, mapping_keys=False):
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


class _FakeResponse:
    status_code = 200
    headers = {}
    is_error = False

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"ok": true}',
                    }
                }
            ]
        }


class _RecordingClient:
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return _FakeResponse()


class KimiTier1ConfigTest(unittest.IsolatedAsyncioTestCase):
    def test_tier1_pacing_is_the_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(kimi._kimi_min_request_interval(), 0.0)

    def test_request_timeout_defaults_to_300_seconds(self):
        timeout_reader = getattr(kimi, "_kimi_request_timeout", None)
        self.assertIsNotNone(timeout_reader)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(timeout_reader(), 300.0)

    def test_structured_schema_omits_nonfunctional_titles(self):
        response_format = kimi.structured_response_format(
            MealPlanDraft,
            "meal_plan",
        )
        schema = response_format["json_schema"]["schema"]

        self.assertNotIn("title", schema)
        for definition in schema["$defs"].values():
            self.assertNotIn("title", definition)
        self.assertIn("$defs", schema)
        self.assertIn("required", schema)

    def test_schema_compaction_preserves_fields_named_like_metadata(self):
        response_format = kimi.structured_response_format(
            MealPlanDraft,
            "meal_plan",
        )
        schema = response_format["json_schema"]["schema"]

        self.assertIn("title", schema["properties"])
        self.assertIn(
            "description",
            schema["$defs"]["RecipeDraft"]["properties"],
        )

    def test_structured_response_format_reuses_contract_schema_builder(self):
        schema_builder = getattr(kimi, "kimi_mfjs_schema", None)
        self.assertIsNotNone(schema_builder)
        with patch.object(
            kimi,
            "kimi_mfjs_schema",
            wraps=schema_builder,
        ) as wrapped:
            response_format = kimi.structured_response_format(
                MealPlanDraft,
                "meal_plan",
            )

        wrapped.assert_called_once_with(MealPlanDraft)
        self.assertEqual(
            response_format["json_schema"]["schema"],
            contracts.kimi_mfjs_schema(MealPlanDraft),
        )

    def test_structured_response_schema_only_has_mfjs_whitelist_keywords(self):
        response_format = kimi.structured_response_format(
            MealPlanDraft,
            "meal_plan",
        )
        schema = response_format["json_schema"]["schema"]

        self.assertLessEqual(
            set(walk_schema_keywords(schema)),
            ALLOWED_WIRE_SCHEMA_KEYS,
        )

    def test_format_repair_prompt_uses_compact_contract_skeleton(self):
        builder = getattr(kimi, "build_format_repair_prompt", None)
        self.assertIsNotNone(builder)
        prompt = builder(
            raw='{"meals":[{"dishes":[]}]}',
            model=MealPlanDraft,
            error_paths=["meals.0.recipes: Field required"],
        )

        self.assertIn(contracts.MODEL_CONTRACT_VERSION, prompt)
        self.assertIn(
            contracts.compact_contract_skeleton(MealPlanDraft),
            prompt,
        )
        self.assertIn('{"meals":[{"dishes":[]}]}', prompt)
        self.assertIn("meals.0.recipes: Field required", prompt)
        self.assertNotIn("$defs", prompt)
        self.assertNotIn("JSON Schema", prompt)

    def test_format_repair_prompt_rejects_oversized_raw_output(self):
        builder = getattr(kimi, "build_format_repair_prompt", None)
        self.assertIsNotNone(builder)

        with self.assertRaises(kimi.AppError) as caught:
            builder(
                raw="x" * 80_001,
                model=MealPlanDraft,
            )

        self.assertEqual(caught.exception.code, "AI_OUTPUT_TRUNCATED")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertTrue(caught.exception.retryable)

    async def test_k26_low_effort_uses_non_thinking_body(self):
        _RecordingClient.requests = []
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _RecordingClient),
        ):
            await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                reasoning_effort="low",
            )

        body = _RecordingClient.requests[0]["json"]
        self.assertEqual(body["model"], "kimi-k2.6")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_effort", body)

    async def test_k27_code_receives_no_reasoning_control_fields(self):
        _RecordingClient.requests = []
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MODEL": "kimi-k2.7-code",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _RecordingClient),
        ):
            await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                reasoning_effort="low",
            )

        body = _RecordingClient.requests[0]["json"]
        self.assertNotIn("thinking", body)
        self.assertNotIn("reasoning_effort", body)

    async def test_k3_receives_reasoning_effort(self):
        _RecordingClient.requests = []
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MODEL": "kimi-k3",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _RecordingClient),
        ):
            await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                reasoning_effort="low",
            )

        body = _RecordingClient.requests[0]["json"]
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertNotIn("thinking", body)

    async def test_k25_low_effort_uses_non_thinking_body(self):
        _RecordingClient.requests = []
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MODEL": "kimi-k2.5",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _RecordingClient),
        ):
            await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                reasoning_effort="low",
            )

        body = _RecordingClient.requests[0]["json"]
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_effort", body)

    async def test_k26_high_effort_enables_thinking(self):
        _RecordingClient.requests = []
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MODEL": "kimi-k2.6",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _RecordingClient),
        ):
            await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                reasoning_effort="high",
            )

        body = _RecordingClient.requests[0]["json"]
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertNotIn("reasoning_effort", body)

    def test_model_prefix_collisions_receive_no_control_fields(self):
        for model in ("kimi-k2.60", "kimi-k2.6x", "kimi-k30", "other"):
            with self.subTest(model=model):
                self.assertEqual(kimi._reasoning_body(model, "low"), {})

    def test_invalid_reasoning_effort_is_rejected(self):
        with self.assertRaises(ValueError):
            kimi._reasoning_body("kimi-k2.6", "LOW")

    async def test_schema_failure_triggers_exactly_one_format_repair(self):
        bad = {
            "role": "assistant",
            "content": '{"title":"旧结构","meals":[]}',
        }
        good_model = MealPlanDraft.model_validate(
            valid_meal_plan_draft_payload()
        )
        calls = []

        async def fake_chat(*args, **kwargs):
            calls.append(kwargs["schema_name"])
            return {
                "role": "assistant",
                "content": good_model.model_dump_json(),
            }

        with patch.object(kimi, "chat_completion", fake_chat):
            parsed = await kimi.parse_or_repair_structured_message(
                api_key="test-key-long-enough",
                message=bad,
                response_model=MealPlanDraft,
                schema_name="meal_plan",
                error_message="结构错误",
                max_completion_tokens=1000,
            )

        self.assertEqual(parsed, good_model)
        self.assertEqual(calls, ["meal_plan_format_repair"])

    async def test_second_schema_failure_maps_to_schema_mismatch(self):
        bad = {
            "role": "assistant",
            "content": '{"title":"旧结构","meals":[]}',
        }

        async def fake_chat(*args, **kwargs):
            return bad

        with patch.object(kimi, "chat_completion", fake_chat):
            with self.assertRaises(kimi.AppError) as caught:
                await kimi.parse_or_repair_structured_message(
                    api_key="test-key-long-enough",
                    message=bad,
                    response_model=MealPlanDraft,
                    schema_name="meal_plan",
                    error_message="结构错误",
                    max_completion_tokens=1000,
                )

        self.assertEqual(caught.exception.code, "AI_SCHEMA_MISMATCH")


if __name__ == "__main__":
    unittest.main()
