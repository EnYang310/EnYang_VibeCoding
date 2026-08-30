from app.lesson_chat import sanitize_learner_work


def test_long_numeric_identifiers_are_removed_before_model_context():
    sanitized = sanitize_learner_work([
        "我的手机号是 13800138000，但我想先保证房租。",
        "银行卡 6222021234567890",
    ])
    joined = " ".join(sanitized)
    assert "13800138000" not in joined
    assert "6222021234567890" not in joined
    assert "[已隐藏数字]" in joined
