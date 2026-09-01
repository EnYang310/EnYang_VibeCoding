from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ChatResponse


def test_chat_endpoint_returns_education_only_reply_without_key(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_SHARED_KEY_PATH", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/v1/lessons/chat",
        json={
            "course_id": "steady-mind",
            "unit_id": "consequence",
            "message": "我现在应该买这个热门标的吗？",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compliance_mode"] == "education_only"
    assert body["source"] == "local_fallback"
    assert "买入" not in body["reply"]


def test_chat_endpoint_passes_multi_turn_history_to_lesson_service(monkeypatch):
    captured = {}

    async def fake_chat(request):
        captured["history"] = request.history
        captured["context"] = request.context
        return ChatResponse(
            reply="你把日期和用途连起来了。再想想：如果日期提前，判断会不会变？",
            evidence_ids=["money-jobs.core-1"],
            evidence_notes=[{"evidence_id": "money-jobs.core-1", "text": "先说清用途和日期。"}],
            learning_signals=["能说明用途"],
            suggested_optional_card=None,
            advance_recommendation="continue",
            compliance_mode="education_only",
            source="kimi",
        )

    monkeypatch.setattr("app.main.personalized_lesson_chat", fake_chat)
    client = TestClient(app)
    response = client.post(
        "/api/v1/lessons/chat",
        json={
            "course_id": "money-jobs",
            "unit_id": "ai-feedback-1",
            "message": "那日期提前呢？",
            "history": [
                {"role": "user", "content": "为什么先看日期？"},
                {"role": "assistant", "content": "因为到期可用是任务的一部分。"},
            ],
            "context": {"answer_summaries": ["回合 2：我先保证近期使用，因为房租日期确定。"], "pending_review_units": [2]},
        },
    )
    assert response.status_code == 200
    assert response.json()["source"] == "kimi"
    assert len(captured["history"]) == 2
    assert captured["history"][0].role == "user"
    assert captured["context"].pending_review_units == [2]


def test_chat_endpoint_rejects_an_empty_message():
    response = TestClient(app).post(
        "/api/v1/lessons/chat",
        json={"course_id": "money-jobs", "unit_id": "ai-feedback-1", "message": ""},
    )
    assert response.status_code == 422


def test_interaction_card_endpoint_executes_the_presentation_tool():
    response = TestClient(app).post(
        "/api/v1/lessons/interaction-card",
        json={"course_id": "money-jobs", "unit_id": "hands-on"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tool_name"] == "present_interaction_card"
    assert body["course_id"] == "money-jobs"
    assert body["unit_id"] == "hands-on"
    assert body["status"] == "presented"


def test_interaction_submission_queues_the_next_card_after_the_teacher_turn(monkeypatch):
    async def fake_chat(request):
        assert "我完成了这张互动卡" in request.message
        assert "本回合回答" in request.context.answer_summaries[-1]
        return ChatResponse(
            reply="你已经把用途和日期连起来了。下一步我们动手排一排。",
            evidence_ids=["money-jobs.core-1"], evidence_notes=[], learning_signals=[],
            suggested_optional_card=None, advance_recommendation="continue", teaching_decision="advance",
            observed_criteria=["能指出不分用途可能造成遗漏、冲突或挤压"], missing_criterion=None,
            compliance_mode="education_only", source="kimi",
        )

    monkeypatch.setattr("app.main.personalized_lesson_chat", fake_chat)
    response = TestClient(app).post(
        "/api/v1/lessons/interaction-turn",
        json={"course_id": "money-jobs", "unit_id": "initial-judgment", "next_unit_id": "hands-on", "submitted_answer": "我先保证下月房租，因为日期最近。", "message": "占位", "history": [], "context": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assistant_reply"]["source"] == "kimi"
    assert body["tool_call"]["tool_name"] == "present_interaction_card"
    assert body["tool_call"]["unit_id"] == "hands-on"


def test_final_action_card_uses_the_same_interaction_reply_envelope(monkeypatch):
    async def fake_chat(request):
        assert request.unit_id == "action-card"
        assert request.context.course_finished is True
        assert request.context.current_card_completed is True
        return ChatResponse(
            reply="你先问使用日期，判断就不会被热闹带跑。这一课的知识点已经讲完了。之后有任何问题，随时问我。",
            evidence_ids=["money-jobs.core-1"], evidence_notes=[], learning_signals=[],
            suggested_optional_card=None, advance_recommendation="stay", teaching_decision="advance",
            observed_criteria=[], missing_criterion=None, compliance_mode="education_only", source="kimi",
        )

    monkeypatch.setattr("app.main.personalized_lesson_chat", fake_chat)
    response = TestClient(app).post(
        "/api/v1/lessons/interaction-turn",
        json={
            "course_id": "money-jobs", "unit_id": "action-card", "next_unit_id": "",
            "submitted_answer": "它最早什么时候要用？", "message": "提交互动卡", "history": [],
            "context": {"current_card_completed": True, "course_finished": True},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_reply"]["reply"].endswith("之后有任何问题，随时问我。")
    assert body["tool_call"] is None
