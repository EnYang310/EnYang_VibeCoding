from app.lesson_runtime import advance_state, get_lesson, local_chat_reply


def test_each_lesson_has_eight_named_units():
    lesson = get_lesson("money-jobs")
    assert lesson is not None
    assert [unit["id"] for unit in lesson["units"]] == [
        "opening",
        "initial-judgment",
        "hands-on",
        "consequence",
        "ai-feedback-1",
        "transfer",
        "ai-feedback-2",
        "action-card",
    ]
    assert len(lesson["evidence"]) >= 3
    assert lesson["sources"]


def test_chat_does_not_advance_course_progress():
    state = {"unit_id": "consequence", "skipped": []}
    reply = local_chat_reply("money-jobs", state["unit_id"], "我怕三个月后钱不够")
    assert reply["advance_recommendation"] in {"stay", "continue"}
    assert state["unit_id"] == "consequence"


def test_skip_marks_unit_for_review_before_advancing():
    state = advance_state("money-jobs", "consequence", action="skip")
    assert state["unit_id"] == "ai-feedback-1"
    assert state["skipped"] == ["consequence"]
