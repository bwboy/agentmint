"""Quota classifier unit tests."""
from services.quota import classify, DEFAULT_QUOTA


def test_ok_state_under_threshold():
    assert classify(0, None) == "ok"
    assert classify(39, None) == "ok"


def test_review_only_band():
    assert classify(40, None) == "review_only"
    assert classify(49, None) == "review_only"


def test_blocked_at_max():
    assert classify(50, None) == "blocked"
    assert classify(100, None) == "blocked"


def test_custom_config_overrides_defaults():
    cfg = {"max": 10, "auto_threshold": 5}
    assert classify(4, cfg) == "ok"
    assert classify(5, cfg) == "review_only"
    assert classify(10, cfg) == "blocked"


def test_default_quota_constants():
    assert DEFAULT_QUOTA["max"] == 50
    assert DEFAULT_QUOTA["auto_threshold"] == 40
