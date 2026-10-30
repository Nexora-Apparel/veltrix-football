from api.telegram import _split_telegram_text


def test_split_telegram_text_preserves_all_fixture_lines():
    lines = [f"Fixture {index}: Home FC vs Away FC" for index in range(1, 180)]
    original = "\n".join(lines)
    chunks = _split_telegram_text(original, limit=3900)

    assert len(chunks) > 1
    assert all(len(chunk) <= 3900 for chunk in chunks)
    delivered = "\n".join(chunks)
    for line in lines:
        assert line in delivered


def test_split_telegram_text_hard_splits_single_oversized_line():
    original = "X" * 8500
    chunks = _split_telegram_text(original, limit=3900)

    assert [len(chunk) for chunk in chunks] == [3900, 3900, 700]
    assert "".join(chunks) == original


def test_split_telegram_text_handles_empty_input():
    assert _split_telegram_text("") == ["No report text was generated."]
