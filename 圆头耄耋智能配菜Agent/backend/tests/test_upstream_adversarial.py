import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import calories, kimi, nutrition
from app.models import FoodLineDraft, RecognizeModelResult
from backend.tests.fakes import (
    ScriptedAsyncClient,
    ScriptedKimi,
    make_response,
)


class KimiUpstreamAdversarialTest(unittest.IsolatedAsyncioTestCase):
    async def _call(self, script):
        ScriptedAsyncClient.configure(script)
        credential = "opaque-" + "credential"
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(
                kimi.httpx,
                "AsyncClient",
                ScriptedAsyncClient,
            ),
        ):
            return await kimi.chat_completion(
                credential,
                [{"role": "user", "content": "adversarial"}],
                123,
                schema_name="adversarial",
            )

    async def test_400_404_and_422_are_stable_request_rejections(self):
        for status in (400, 404, 422):
            with self.subTest(status=status):
                with self.assertRaises(kimi.AppError) as caught:
                    await self._call([make_response(status)])

                self.assertEqual(caught.exception.code, "AI_REQUEST_REJECTED")
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    async def test_401_and_403_are_stable_authentication_failures(self):
        for status in (401, 403):
            with self.subTest(status=status):
                with self.assertRaises(kimi.AppError) as caught:
                    await self._call([make_response(status)])

                self.assertEqual(caught.exception.code, "API_KEY_INVALID")
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    async def test_5xx_are_retryable_without_hidden_http_retries(self):
        for status in (500, 502, 503):
            with self.subTest(status=status):
                with self.assertRaises(kimi.AppError) as caught:
                    await self._call([make_response(status)])

                self.assertEqual(caught.exception.code, "AI_UNAVAILABLE")
                self.assertTrue(caught.exception.retryable)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    async def test_dns_and_timeout_have_distinct_stable_error_codes(self):
        request = httpx.Request(
            "POST",
            "https://example.test/v1/chat/completions",
        )
        cases = (
            (
                httpx.ConnectError("dns unavailable", request=request),
                "AI_UNAVAILABLE",
            ),
            (
                httpx.ReadTimeout("upstream timed out", request=request),
                "AI_TIMEOUT",
            ),
        )
        for upstream_error, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(kimi.AppError) as caught:
                    await self._call([upstream_error])

                self.assertEqual(caught.exception.code, expected_code)
                self.assertTrue(caught.exception.retryable)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    async def test_429_has_exactly_three_attempts_and_two_backoffs(self):
        responses = [make_response(429) for _ in range(3)]

        with patch.object(kimi.asyncio, "sleep", new=AsyncMock()) as sleep:
            with self.assertRaises(kimi.AppError) as caught:
                await self._call(responses)

        self.assertEqual(caught.exception.code, "AI_RATE_LIMITED")
        self.assertEqual(ScriptedAsyncClient.call_count, 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_malformed_success_responses_have_stable_codes(self):
        cases = (
            (make_response(200, text="<html>gateway</html>"), "AI_BAD_RESPONSE"),
            (make_response(200, payload={"choices": []}), "AI_EMPTY_RESPONSE"),
            (
                make_response(
                    200,
                    payload={
                        "choices": [
                            {
                                "finish_reason": "length",
                                "message": {
                                    "role": "assistant",
                                    "content": '{"partial":',
                                },
                            }
                        ]
                    },
                ),
                "AI_OUTPUT_TRUNCATED",
            ),
        )
        for response, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(kimi.AppError) as caught:
                    await self._call([response])

                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    def test_bad_structured_json_is_not_silently_accepted(self):
        with self.assertRaises(kimi.AppError) as caught:
            kimi.parse_structured_message(
                {"role": "assistant", "content": "{not-json"},
                RecognizeModelResult,
                "bad structure",
            )

        self.assertEqual(caught.exception.code, "AI_BAD_RESPONSE")

    async def test_bad_json_gets_exactly_one_format_repair(self):
        fake = ScriptedKimi(
            [
                {
                    "role": "assistant",
                    "content": '{"ingredients":[],"warnings":[]}',
                }
            ]
        )

        with patch.object(kimi, "chat_completion", new=fake):
            result = await kimi.parse_or_repair_structured_message(
                api_key="opaque-" + "credential",
                message={"role": "assistant", "content": "{not-json"},
                response_model=RecognizeModelResult,
                schema_name="recognized_ingredients",
                error_message="bad structure",
                max_completion_tokens=123,
            )

        self.assertEqual(result.ingredients, [])
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(
            fake.calls[0]["schema_name"],
            "recognized_ingredients_format_repair",
        )

    async def test_failed_repair_does_not_trigger_a_second_repair(self):
        fake = ScriptedKimi(
            [{"role": "assistant", "content": "{still-not-json"}]
        )

        with (
            patch.object(kimi, "chat_completion", new=fake),
            self.assertRaises(kimi.AppError) as caught,
        ):
            await kimi.parse_or_repair_structured_message(
                api_key="opaque-" + "credential",
                message={"role": "assistant", "content": "{not-json"},
                response_model=RecognizeModelResult,
                schema_name="recognized_ingredients",
                error_message="bad structure",
                max_completion_tokens=123,
            )

        self.assertEqual(caught.exception.code, "AI_SCHEMA_MISMATCH")
        self.assertEqual(fake.call_count, 1)


class NutritionUpstreamAdversarialTest(unittest.IsolatedAsyncioTestCase):
    async def test_usda_network_and_local_db_failures_degrade_to_no_match(self):
        request = httpx.Request("POST", nutrition.FDC_API_URL)
        with (
            patch.object(
                nutrition,
                "search_local_nutrition",
                new=AsyncMock(side_effect=RuntimeError("database unavailable")),
            ),
            patch.object(
                nutrition,
                "fetch_online_usda_nutrition",
                new=AsyncMock(
                    side_effect=httpx.ConnectError(
                        "network unavailable",
                        request=request,
                    )
                ),
            ),
        ):
            result = await nutrition.resolve_nutrition(
                "tomatoes red ripe raw",
                "tomatoes raw",
            )

        self.assertIsNone(result)

    async def test_malformed_local_database_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "nutrition.db"
            malformed.write_bytes(b"not a sqlite database")

            with patch.object(nutrition, "LOCAL_DB_PATH", malformed):
                result = await nutrition.search_local_nutrition(
                    "tomatoes red ripe raw"
                )

        self.assertIsNone(result)

    async def test_usda_html_and_invalid_payloads_are_ignored(self):
        cases = (
            make_response(200, text="<html>gateway</html>"),
            make_response(200, payload={"foods": "not-a-list"}),
            make_response(200, payload={"foods": []}),
        )
        for response in cases:
            with self.subTest(response=response):
                ScriptedAsyncClient.configure([response])
                with (
                    patch.object(
                        nutrition,
                        "_read_cache",
                        return_value=None,
                    ),
                    patch.object(
                        nutrition.httpx,
                        "AsyncClient",
                        ScriptedAsyncClient,
                    ),
                ):
                    result = await nutrition.fetch_online_usda_nutrition(
                        "tomatoes red ripe raw"
                    )

                self.assertIsNone(result)
                self.assertEqual(ScriptedAsyncClient.call_count, 1)

    async def test_batch_resolution_coalesces_twenty_identical_queries(self):
        line = FoodLineDraft(
            name="番茄",
            nutritionQuery="tomatoes red ripe raw",
            nutritionFallbackQuery="tomatoes raw",
            grams=100,
            note="",
            estimatedKcalPer100g=18,
        )
        lookup = AsyncMock(return_value=None)

        with patch.object(calories, "fetch_usda_nutrition", new=lookup):
            matches = await calories._resolve_matches([line] * 20)

        lookup.assert_awaited_once_with(
            "tomatoes red ripe raw",
            "tomatoes raw",
        )
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
