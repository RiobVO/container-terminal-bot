"""Тесты services.telegram_utils."""
from services.telegram_utils import split_text


def test_short_text_returned_as_single_chunk():
    """Короткий текст возвращается одним куском, без изменений."""
    text = "короткий текст"
    assert split_text(text) == [text]


def test_exact_limit_returned_as_single_chunk():
    """Текст ровно по лимиту — один кусок."""
    text = "a" * 4000
    assert split_text(text, max_len=4000) == [text]


def test_long_text_split_by_newlines():
    """Длинный текст режется по \\n, ни одна часть не превышает лимит."""
    lines = [f"строка {i}" * 10 for i in range(200)]
    text = "\n".join(lines)
    chunks = split_text(text, max_len=500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 500


def test_single_line_longer_than_limit_is_force_split():
    """Одна строка длиннее лимита — режется пополам, не зависает."""
    text = "a" * 1000
    chunks = split_text(text, max_len=100)
    assert all(len(c) <= 100 for c in chunks)
    # Сумма восстанавливает исходник
    assert "".join(chunks) == text


def test_preserves_content():
    """Склейка чанков с \\n восстанавливает исходный текст."""
    text = "\n".join(f"line{i}" for i in range(500))
    chunks = split_text(text, max_len=200)
    assert "\n".join(chunks) == text
