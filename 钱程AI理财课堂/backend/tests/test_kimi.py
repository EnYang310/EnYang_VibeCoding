import pytest
import httpx

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


@pytest.mark.asyncio
async def test_lesson_generation_cancels_the_provider_attempt_at_ninety_seconds(monkeypatch):
    attempts = []

    class TimedOutClient:
        def __init__(self, *, timeout):
            attempts.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("model took too long")

    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key-is-long-enough")
    monkeypatch.setattr("app.kimi.httpx.AsyncClient", TimedOutClient)

    result = await KimiClient().lesson_chat(
        course_title="钱程课",
        unit_title="先看日期",
        learning_focus="先看用途和日期",
        evidence=[{"evidence_id": "money-jobs.core-1", "text": "先看用途。", "boundary": "只做学习解释"}],
        message="我选了先留房租。",
        history=[],
        learner_work=[],
        pending_review_units=[],
        advancement_criteria=[],
        course_finished=False,
        free_chat_mode=False,
        offer_transition=True,
        compliance_redirect=False,
    )

    assert result is None
    assert attempts == [90.0]
