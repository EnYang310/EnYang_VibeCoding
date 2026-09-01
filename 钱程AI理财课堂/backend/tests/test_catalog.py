from app.course_data import COURSE_IDS, get_course, list_courses


def test_catalog_contains_the_eight_planned_courses():
    assert COURSE_IDS == (
        "money-jobs",
        "safety-net",
        "product-map",
        "tradeoffs",
        "future-date",
        "steady-mind",
        "fund-stock-basics",
        "volatility-time",
    )
    assert len(list_courses()) == 8


def test_every_course_has_complete_learning_metadata():
    for course_id in COURSE_IDS:
        course = get_course(course_id)
        assert course["title"]
        assert course["subtitle"]
        assert course["learning_goal"]
        assert course["disclaimer"] == "仅作学习模拟，不构成投资建议。"
