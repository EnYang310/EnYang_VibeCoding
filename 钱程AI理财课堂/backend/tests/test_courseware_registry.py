from app.courseware import evidence_for_unit, load_courseware


def test_all_eight_courses_have_separate_parseable_courseware():
    for course_id in (
        "money-jobs", "safety-net", "product-map", "tradeoffs", "future-date", "steady-mind",
        "fund-stock-basics", "volatility-time",
    ):
        courseware = load_courseware(course_id)
        assert courseware.course_id == course_id
        assert len(courseware.evidence) >= 3
        assert all(item.text and item.evidence_id.startswith(f"{course_id}.") for item in courseware.evidence)
        assert courseware.sources
        assert all(source.startswith("https://") for source in courseware.sources)


def test_teacher_units_get_only_evidence_from_their_own_courseware():
    evidence = evidence_for_unit("steady-mind", "ai-feedback-2")
    assert {item.evidence_id for item in evidence} == {
        "steady-mind.core-1", "steady-mind.core-2", "steady-mind.core-3", "steady-mind.core-4"
    }
