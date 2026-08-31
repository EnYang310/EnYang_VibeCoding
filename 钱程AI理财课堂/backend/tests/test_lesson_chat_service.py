import pytest

from app.kimi import _safe_chat_generated
from app.lesson_chat import personalized_lesson_chat, sanitize_user_text
from app.schemas import ChatRequest


def test_generated_reply_rejects_evidence_outside_current_lesson():
    result = _safe_chat_generated(
        {
            "reply": "先把用途和日期说清楚，再看这笔钱到时是否可用。",
            "evidence_ids": ["other-course.core-9"],
            "learning_signals": [],
            "advance_recommendation": "stay",
        },
        allowed_evidence_ids={"money-jobs.core-1"},
    )
    assert result is None


def test_generated_reply_rejects_transaction_instruction():
    result = _safe_chat_generated(
        {
            "reply": "这个情况建议你买入某基金。",
            "evidence_ids": ["money-jobs.core-1"],
            "learning_signals": [],
            "advance_recommendation": "stay",
        },
        allowed_evidence_ids={"money-jobs.core-1"},
    )
    assert result is None


def test_generated_reply_keeps_a_partial_teacher_scene_instead_of_discarding_the_turn():
    result = _safe_chat_generated(
        {
            "reply": "先把下月房租留出来，这个判断先抓住了日期。",
            "evidence_ids": ["money-jobs.core-1"],
            "teaching_scene": {
                "screen_title": "先看日期",
                # Models sometimes return a string instead of the requested
                # array, or fewer beats than the ideal teaching rhythm.  That
                # should render as a usable lesson, not trigger another full
                # model generation.
                "full_caption": "房租日期最近，所以它不是一笔可以随意挪用的钱。先把近期用途留住，才有后面的选择。",
                "teaching_artifacts": [{"kind": "unexpected-layout", "title": "忽略这一项"}],
            },
        },
        allowed_evidence_ids={"money-jobs.core-1"},
    )

    assert result is not None
    assert result.teaching_scene is not None
    assert result.teaching_scene.full_caption == ["房租日期最近，所以它不是一笔可以随意挪用的钱。先把近期用途留住，才有后面的选择。"]
    assert result.teaching_scene.teaching_artifacts == []


@pytest.mark.parametrize(
    "reply",
    [
        "今天就买贵州茅台。",
        "把仓位调到七成更合适。",
        "可以按60%配置沪深300。",
        "直接购买代码为510300的产品。",
    ],
)
def test_generated_reply_rejects_indirect_or_numeric_transaction_instruction(reply):
    result = _safe_chat_generated(
        {
            "reply": reply,
            "evidence_ids": ["money-jobs.core-1"],
            "learning_signals": [],
            "advance_recommendation": "stay",
        },
        allowed_evidence_ids={"money-jobs.core-1"},
    )
    assert result is None


def test_user_text_masks_accounts_passwords_and_verification_codes():
    sanitized = sanitize_user_text("姓名小王，卡号 6222-0212-3456-7890，验证码 123456，密码 abc123")
    assert "6222" not in sanitized
    assert "123456" not in sanitized
    assert "abc123" not in sanitized
    assert "[已隐藏" in sanitized


@pytest.mark.asyncio
async def test_real_transaction_question_never_reaches_the_model(monkeypatch):
    called = False

    async def fake_lesson_chat(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("real transaction request must not reach model")

    monkeypatch.setattr("app.lesson_chat.KimiClient.lesson_chat", fake_lesson_chat)
    response = await personalized_lesson_chat(
        ChatRequest(course_id="steady-mind", unit_id="ai-feedback-2", message="今天具体买哪只基金？")
    )
    assert called is False
    assert response.source == "local_fallback"
    assert response.compliance_mode == "education_only"


@pytest.mark.asyncio
async def test_missing_key_falls_back_to_courseware_reply(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_SHARED_KEY_PATH", raising=False)
    response = await personalized_lesson_chat(
        ChatRequest(course_id="product-map", unit_id="ai-feedback-1", message="流动性是什么意思？")
    )
    assert response.source == "local_fallback"
    assert response.evidence_ids[0].startswith("product-map.")
    assert response.evidence_notes
    assert response.evidence_notes[0].text
    assert "推荐" not in response.reply


@pytest.mark.asyncio
async def test_completed_interaction_uses_the_fast_courseware_teacher_without_waiting_for_the_model(monkeypatch):
    called = False

    async def fake_lesson_chat(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("a completed card must use the immediate lesson path")

    monkeypatch.setattr("app.lesson_chat.KimiClient.lesson_chat", fake_lesson_chat)
    response = await personalized_lesson_chat(
        ChatRequest(
            course_id="money-jobs",
            unit_id="initial-judgment",
            message="我完成了这张互动卡。我的回答是：先留出下月房租。",
            context={"current_card_completed": True, "current_card_answer": "先留出下月房租。"},
        )
    )

    assert called is False
    assert response.source == "local_fallback"
    assert response.teaching_scene is not None
    assert len(response.teaching_scene.full_caption) == 6
    assert "自己的生活里" in response.reply
