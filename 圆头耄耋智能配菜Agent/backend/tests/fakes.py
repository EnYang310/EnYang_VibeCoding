import asyncio
from typing import Any, Dict, Iterable, List, Optional

import httpx


def make_response(
    status: int = 200,
    *,
    payload: Optional[Any] = None,
    text: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.Response:
    request = httpx.Request(
        "POST",
        "https://example.test/v1/chat/completions",
    )
    if text is not None:
        return httpx.Response(
            status,
            text=text,
            headers=headers,
            request=request,
        )
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
        headers=headers,
        request=request,
    )


class ScriptedAsyncClient:
    script: List[Any] = []
    requests: List[Dict[str, Any]] = []
    call_count = 0

    @classmethod
    def configure(cls, script: Iterable[Any]) -> None:
        cls.script = list(script)
        cls.requests = []
        cls.call_count = 0

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, **kwargs):
        if not self.__class__.script:
            raise AssertionError("unexpected unscripted HTTP call")
        self.__class__.call_count += 1
        self.__class__.requests.append({"url": url, **kwargs})
        result = self.__class__.script.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class ScriptedKimi:
    def __init__(self, script: Iterable[Any]):
        self._script = list(script)
        self.calls: List[Dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def __call__(
        self,
        _api_key: str,
        messages,
        max_completion_tokens: int,
        **kwargs,
    ):
        if not self._script:
            raise AssertionError("unexpected unscripted Kimi call")
        self.calls.append(
            {
                "messages": messages,
                "max_completion_tokens": max_completion_tokens,
                **kwargs,
            }
        )
        result = self._script.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class CountingAsyncRunner:
    def __init__(
        self,
        *,
        result: Any = None,
        error: Optional[BaseException] = None,
        gate: Optional[asyncio.Event] = None,
    ):
        self.result = result
        self.error = error
        self.gate = gate
        self.call_count = 0

    async def __call__(self, _progress):
        self.call_count += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return self.result
