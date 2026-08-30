from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_taro_client_contains_all_six_course_ids():
    source = (ROOT / "client" / "src" / "course-content.ts").read_text(encoding="utf-8")
    for course_id in (
        "money-jobs", "safety-net", "product-map", "tradeoffs", "future-date", "steady-mind"
    ):
        assert f"'{course_id}'" in source


def test_h5_and_weapp_use_separate_build_outputs():
    config = (ROOT / "client" / "config" / "index.ts").read_text(encoding="utf-8")
    assert "dist/weapp" in config
    assert "dist/h5" in config
    assert "publicPath: './'" in config


def test_classroom_uses_multi_turn_chat_and_explicit_progress_engine():
    page = (ROOT / "client" / "src" / "pages" / "index" / "index.tsx").read_text(encoding="utf-8")
    assert "/api/v1/lessons/chat" in page
    assert "history: previous.slice(-6)" in page
    assert "advanceCourse" in page
    assert "skipCourseUnit" in page
    assert "openReviewUnit" in page
