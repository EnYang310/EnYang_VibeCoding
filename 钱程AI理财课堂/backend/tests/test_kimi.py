import pytest
import httpx
import json

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


@pytest.mark.asyncio
async def test_final_card_prompt_requires_the_closing_in_the_spoken_caption(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "reply": "你先问日期。",
                "evidence_ids": ["money-jobs.core-1"],
            }, ensure_ascii=False)}}]}

    class SuccessfulClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return SuccessfulResponse()

    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key-is-long-enough")
    monkeypatch.setattr("app.kimi.httpx.AsyncClient", SuccessfulClient)
    client = KimiClient()
    original_request_body = client.request_body

    def capture_request_body(prompt):
        captured["prompt"] = prompt
        return original_request_body(prompt)

    monkeypatch.setattr(client, "request_body", capture_request_body)
    await client.lesson_chat(
        course_title="钱程课", unit_title="课后带走一句话", learning_focus="先看用途和日期",
        evidence=[{"evidence_id": "money-jobs.core-1", "text": "先看用途。", "boundary": "只做学习解释"}],
        message="我选了先问日期。", history=[], learner_work=[], pending_review_units=[], advancement_criteria=[],
        course_finished=True, free_chat_mode=False, offer_transition=True, compliance_redirect=False,
    )

    assert captured["prompt"]["lesson_stage"] == "final_action_card"
    assert any("full_caption 的最后一段" in rule for rule in captured["prompt"]["rules"])


@pytest.mark.asyncio
async def test_free_chat_prompt_keeps_the_complete_teaching_scene(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "reply": "先把这个概念放回生活里看。",
                "evidence_ids": ["money-jobs.core-1"],
            }, ensure_ascii=False)}}]}

    class SuccessfulClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return SuccessfulResponse()

    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key-is-long-enough")
    monkeypatch.setattr("app.kimi.httpx.AsyncClient", SuccessfulClient)
    client = KimiClient()
    original_request_body = client.request_body

    def capture_request_body(prompt):
        captured["prompt"] = prompt
        return original_request_body(prompt)

    monkeypatch.setattr(client, "request_body", capture_request_body)
    await client.lesson_chat(
        course_title="钱程课", unit_title="课后自由问答", learning_focus="先看用途和日期",
        evidence=[{"evidence_id": "money-jobs.core-1", "text": "先看用途。", "boundary": "只做学习解释"}],
        message="那基金到底怎么分散风险？", history=[], learner_work=[], pending_review_units=[], advancement_criteria=[],
        course_finished=False, free_chat_mode=True, offer_transition=False, compliance_redirect=False,
    )

    assert any("full_caption 必须是 6 到 8 段" in rule for rule in captured["prompt"]["rules"])
