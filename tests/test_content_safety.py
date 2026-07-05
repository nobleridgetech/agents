from noble_ridge_agents.content_safety import mask_sensitive_text, truncate_text


def test_mask_sensitive_text_redacts_common_secret_bearing_values():
    raw = (
        "Email me at client@example.com or visit https://example.com/reset?token=abc. "
        "Token ghp_12...wxyz and phone 555-123-4567. Mention @nobleridgetech."
    )

    masked = mask_sensitive_text(raw)

    assert "client@example.com" not in masked
    assert "https://example.com" not in masked
    assert "ghp_12...wxyz" not in masked
    assert "555-123-4567" not in masked
    assert "@nobleridgetech" not in masked
    assert "[redacted-email]" in masked
    assert "[redacted-url]" in masked
    assert "[redacted-token]" in masked
    assert "[redacted-phone]" in masked
    assert "[redacted-handle]" in masked


def test_truncate_text_keeps_short_text_and_marks_long_text():
    assert truncate_text("short", max_chars=10) == "short"

    truncated = truncate_text("abcdefghijklmnopqrstuvwxyz", max_chars=10)

    assert truncated == "abcdefghij… [truncated]"
