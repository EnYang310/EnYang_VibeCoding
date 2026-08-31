from app.teaching_flow import (
    COURSE_FINISHED_CLOSING,
    MAX_ASSISTANT_REPLIES_BETWEEN_CARDS,
    append_course_finished_closing,
    append_follow_up_hook,
    has_dense_artifact_cadence,
    has_short_caption_beats,
    should_present_next_card,
)


def test_forces_the_next_card_on_the_third_teacher_reply():
    assert should_present_next_card(
        current_card_completed=True,
        course_finished=False,
        next_unit_id="hands-on",
        assistant_replies_since_card=MAX_ASSISTANT_REPLIES_BETWEEN_CARDS - 1,
        gate_passed=False,
    ) is True


def test_does_not_force_cards_after_the_course_is_complete():
    assert should_present_next_card(
        current_card_completed=True,
        course_finished=True,
        next_unit_id="action-card",
        assistant_replies_since_card=MAX_ASSISTANT_REPLIES_BETWEEN_CARDS,
        gate_passed=True,
    ) is False


def test_allows_an_early_card_after_the_learning_gate_is_met():
    assert should_present_next_card(
        current_card_completed=True,
        course_finished=False,
        next_unit_id="hands-on",
        assistant_replies_since_card=0,
        gate_passed=True,
    ) is True


def test_requires_a_teaching_component_after_each_short_caption_beat():
    assert has_dense_artifact_cadence(paragraph_count=4, appear_after_paragraphs=[0, 1, 2]) is True
    assert has_dense_artifact_cadence(paragraph_count=4, appear_after_paragraphs=[0, 2]) is False


def test_caption_beats_are_limited_to_two_or_three_sentences():
    assert has_short_caption_beats([
        "先看用途。再看日期。",
        "日期近时要先保证可用。这样才不会被临时支出挤掉。",
        "先把任务分开。再决定下一步。",
    ]) is True
    assert has_short_caption_beats(["这段只写了一句话。", "再看日期。然后再看用途。", "最后回到生活。再想一步。"]) is False


def test_final_card_reply_always_closes_the_course_into_free_questions():
    reply = append_course_finished_closing("你把用途、日期和下一步连起来了。")
    assert COURSE_FINISHED_CLOSING in reply


def test_normal_teacher_reply_always_ends_with_a_specific_follow_up_hook():
    reply = append_follow_up_hook("先把这笔钱的用途和日期分开看。", "先想想这笔钱最早什么时候必须用。")
    assert reply.endswith("先想想这笔钱最早什么时候必须用。")
