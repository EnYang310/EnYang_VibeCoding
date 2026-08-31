"""Deterministic teaching rhythm around AI-generated explanations."""

from __future__ import annotations

import re


MAX_ASSISTANT_REPLIES_BETWEEN_CARDS = 2
COURSE_FINISHED_CLOSING = "这一课的知识点已经讲完了。之后有任何问题，随时问我。"


def should_present_next_card(
    *,
    current_card_completed: bool,
    course_finished: bool,
    next_unit_id: str,
    assistant_replies_since_card: int,
    gate_passed: bool,
) -> bool:
    """Return whether the reply being generated must be followed by a card.

    ``assistant_replies_since_card`` counts replies already delivered after the
    learner submitted the current choice.  The teacher may give up to two
    full explanations before the next exercise arrives after narration ends.
    """
    if course_finished or not current_card_completed or not next_unit_id:
        return False
    return gate_passed or assistant_replies_since_card + 1 >= MAX_ASSISTANT_REPLIES_BETWEEN_CARDS


def has_dense_artifact_cadence(*, paragraph_count: int, appear_after_paragraphs: list[int]) -> bool:
    """One adaptable visual explanation follows every 2–3-sentence beat.

    Captions are deliberately authored as a complete classroom explanation.
    For a 6–8 paragraph narration, visual beats must cover every paragraph
    except the final landing sentence.
    """
    if paragraph_count < 6 or paragraph_count > 8:
        return False
    required = set(range(paragraph_count - 1))
    return required.issubset(set(appear_after_paragraphs))


def has_short_caption_beats(paragraphs: list[str]) -> bool:
    """Keep each visible/audio beat at two or three Chinese sentences."""
    if not 6 <= len(paragraphs) <= 8:
        return False
    return all(2 <= len([item for item in re.split(r"[。！？!?]+", paragraph) if item.strip()]) <= 3 for paragraph in paragraphs)


def append_course_finished_closing(reply: str) -> str:
    cleaned = reply.strip()
    if COURSE_FINISHED_CLOSING in cleaned:
        return cleaned
    return f"{cleaned.rstrip('。！？!?')}。{COURSE_FINISHED_CLOSING}"


def append_follow_up_hook(reply: str, hook: str) -> str:
    """End a normal teaching turn with one concrete invitation to continue.

    The final action-card turn deliberately uses ``append_course_finished_closing``
    instead, so the lesson can land instead of manufacturing another prompt.
    """
    cleaned_reply = reply.strip().rstrip("。！？!?")
    cleaned_hook = hook.strip()
    if not cleaned_hook or cleaned_hook in cleaned_reply:
        return cleaned_reply + "。"
    return f"{cleaned_reply}。{cleaned_hook}"
