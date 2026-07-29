import unittest

import httpx

from backend.tests.fakes import (
    CountingAsyncRunner,
    ScriptedAsyncClient,
    ScriptedKimi,
    make_response,
)


class AdversarialFakeTest(unittest.IsolatedAsyncioTestCase):
    async def test_scripted_kimi_records_stage_and_consumes_once(self):
        fake = ScriptedKimi(
            [
                {
                    "role": "assistant",
                    "content": '{"ok":true}',
                }
            ]
        )

        result = await fake(
            "secret-key-never-recorded",
            [{"role": "user", "content": "test"}],
            123,
            schema_name="meal_plan",
        )

        self.assertEqual(result["content"], '{"ok":true}')
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(fake.calls[0]["schema_name"], "meal_plan")
        self.assertNotIn("api_key", fake.calls[0])
        with self.assertRaises(AssertionError):
            await fake(
                "secret-key-never-recorded",
                [],
                1,
                schema_name="unexpected",
            )

    async def test_scripted_http_client_counts_requests_and_exceptions(self):
        ScriptedAsyncClient.configure(
            [
                make_response(429),
                httpx.ConnectError("offline"),
            ]
        )

        async with ScriptedAsyncClient() as client:
            response = await client.post(
                "https://example.test/v1/chat/completions",
                json={"model": "fake"},
            )
            self.assertEqual(response.status_code, 429)
            with self.assertRaises(httpx.ConnectError):
                await client.post(
                    "https://example.test/v1/chat/completions",
                    json={"model": "fake"},
                )

        self.assertEqual(ScriptedAsyncClient.call_count, 2)
        self.assertEqual(len(ScriptedAsyncClient.requests), 2)
        with self.assertRaises(AssertionError):
            async with ScriptedAsyncClient() as client:
                await client.post("https://example.test")

    async def test_counting_runner_records_one_call(self):
        runner = CountingAsyncRunner(result={"ok": True})

        result = await runner(lambda _phase, _message: None)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
