import pytest

from app.kimi import KimiClient


@pytest.mark.asyncio
async def test_missing_key_returns_unavailable_without_network(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_SHARED_KEY_PATH", raising=False)
    client = KimiClient()
    assert await client.available() is False


def test_k2_6_short_feedback_request_uses_its_required_temperature(monkeypatch):
    monkeypatch.setenv("KIMI_MODEL", "kimi-k2.6")
    client = KimiClient()

    assert client.request_body({"example": "payload"})["temperature"] == 0.6


def test_k2_6_feedback_turns_off_extended_thinking_for_a_short_lesson_reply(monkeypatch):
    monkeypatch.setenv("KIMI_MODEL", "kimi-k2.6")
    client = KimiClient()

    assert client.request_body({"example": "payload"})["thinking"] == {"type": "disabled"}
