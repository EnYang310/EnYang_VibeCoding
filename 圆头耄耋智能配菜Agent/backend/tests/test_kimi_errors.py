import os
import unittest
from typing import Optional
from unittest.mock import AsyncMock, patch

import httpx

from app import kimi


def _response(
    status: int = 200,
    *,
    payload=None,
    text: Optional[str] = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(
        status,
        json=payload
        if payload is not None
        else {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": '{"ok":true}',
                    },
                }
            ]
        },
        request=request,
    )


class _ScriptedClient:
    responses = []
    requests = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class KimiErrorMappingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _ScriptedClient.responses = []
        _ScriptedClient.requests = []

    async def _call(self):
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _ScriptedClient),
        ):
            return await kimi.chat_completion(
                "test-key-long-enough",
                [{"role": "user", "content": "测试"}],
                123,
                schema_name="test_stage",
            )

    async def test_400_maps_to_request_rejected_without_retry(self):
        _ScriptedClient.responses = [_response(400)]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_REQUEST_REJECTED")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(len(_ScriptedClient.requests), 1)

    async def test_404_and_422_map_to_request_rejected(self):
        for status in (404, 422):
            with self.subTest(status=status):
                _ScriptedClient.responses = [_response(status)]
                _ScriptedClient.requests = []

                with self.assertRaises(kimi.AppError) as caught:
                    await self._call()

                self.assertEqual(
                    caught.exception.code,
                    "AI_REQUEST_REJECTED",
                )
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(len(_ScriptedClient.requests), 1)

    async def test_403_maps_to_api_key_invalid(self):
        _ScriptedClient.responses = [_response(403)]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "API_KEY_INVALID")
        self.assertEqual(caught.exception.status_code, 401)
        self.assertFalse(caught.exception.retryable)

    async def test_401_maps_to_api_key_invalid(self):
        _ScriptedClient.responses = [_response(401)]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "API_KEY_INVALID")
        self.assertEqual(caught.exception.status_code, 401)

    async def test_non_json_200_maps_to_bad_response(self):
        _ScriptedClient.responses = [_response(200, text="<html>oops</html>")]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_BAD_RESPONSE")
        self.assertTrue(caught.exception.retryable)

    async def test_empty_choices_maps_to_empty_response(self):
        _ScriptedClient.responses = [_response(200, payload={"choices": []})]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_EMPTY_RESPONSE")

    async def test_length_finish_reason_maps_to_output_truncated(self):
        _ScriptedClient.responses = [
            _response(
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
            )
        ]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_OUTPUT_TRUNCATED")
        self.assertTrue(caught.exception.retryable)

    async def test_429_retries_three_attempts_then_maps_rate_limit(self):
        _ScriptedClient.responses = [
            _response(429),
            _response(429),
            _response(429),
        ]

        with patch.object(kimi.asyncio, "sleep", new=AsyncMock()) as sleep:
            with self.assertRaises(kimi.AppError) as caught:
                await self._call()

        self.assertEqual(caught.exception.code, "AI_RATE_LIMITED")
        self.assertEqual(caught.exception.status_code, 429)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(len(_ScriptedClient.requests), 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_500_maps_to_retryable_unavailable_without_retry(self):
        _ScriptedClient.responses = [_response(500)]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_UNAVAILABLE")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(len(_ScriptedClient.requests), 1)

    async def test_other_5xx_maps_to_retryable_unavailable(self):
        for status in (502, 503):
            with self.subTest(status=status):
                _ScriptedClient.responses = [_response(status)]
                _ScriptedClient.requests = []

                with self.assertRaises(kimi.AppError) as caught:
                    await self._call()

                self.assertEqual(caught.exception.code, "AI_UNAVAILABLE")
                self.assertTrue(caught.exception.retryable)
                self.assertEqual(len(_ScriptedClient.requests), 1)

    async def test_logs_and_error_never_include_api_key(self):
        secret = "test-secret-key-that-must-not-leak"
        _ScriptedClient.responses = [_response(403)]
        with (
            patch.dict(
                os.environ,
                {
                    "MOONSHOT_BASE_URL": "https://example.test/v1",
                    "KIMI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                },
                clear=True,
            ),
            patch.object(kimi.httpx, "AsyncClient", _ScriptedClient),
            self.assertLogs("uvicorn.error", level="INFO") as captured,
        ):
            with self.assertRaises(kimi.AppError) as caught:
                await kimi.chat_completion(
                    secret,
                    [{"role": "user", "content": "测试"}],
                    123,
                )

        self.assertNotIn(secret, "\n".join(captured.output))
        self.assertNotIn(secret, str(caught.exception))

    async def test_success_log_exposes_cost_metrics_and_contract(self):
        _ScriptedClient.responses = [
            _response(
                200,
                payload={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": '{"ok":true}',
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "total_tokens": 150,
                        "prompt_tokens_details": {
                            "cached_tokens": 40,
                        },
                    },
                },
            )
        ]

        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            await self._call()

        events = [
            getattr(record, "kimi_event", None)
            for record in captured.records
            if getattr(record, "kimi_event", None) is not None
        ]
        self.assertEqual(1, len(events))
        self.assertEqual("kimi-k2.6", events[0]["model"])
        self.assertEqual("maodie-model-contract-1.7.0", events[0]["contractVersion"])
        self.assertEqual(120, events[0]["inputTokens"])
        self.assertEqual(30, events[0]["outputTokens"])
        self.assertEqual(40, events[0]["cachedTokens"])
        self.assertEqual("stop", events[0]["finishReason"])
        self.assertGreaterEqual(events[0]["elapsedSeconds"], 0)

    async def test_network_failure_maps_to_unavailable(self):
        _ScriptedClient.responses = [
            httpx.ConnectError(
                "dns failed",
                request=httpx.Request(
                    "POST",
                    "https://example.test/v1/chat/completions",
                ),
            )
        ]

        with self.assertRaises(kimi.AppError) as caught:
            await self._call()

        self.assertEqual(caught.exception.code, "AI_UNAVAILABLE")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertTrue(caught.exception.retryable)


if __name__ == "__main__":
    unittest.main()
