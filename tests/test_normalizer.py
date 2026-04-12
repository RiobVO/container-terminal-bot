"""Тесты нормализации номера контейнера (ISO 6346)."""

from services.normalizer import normalize_container_number


def test_valid_number():
    """Стандартный номер без пробелов."""
    result = normalize_container_number("TEMU6275401")
    assert result == ("TEMU6275401", "TEMU 6275401")


def test_valid_with_space():
    """Номер с пробелом между буквами и цифрами."""
    result = normalize_container_number("TEMU 6275401")
    assert result == ("TEMU6275401", "TEMU 6275401")


def test_lowercase():
    """Нижний регистр приводится к верхнему."""
    result = normalize_container_number("temu6275401")
    assert result == ("TEMU6275401", "TEMU 6275401")


def test_with_dash():
    """Дефис удаляется."""
    result = normalize_container_number("TEMU-6275401")
    assert result == ("TEMU6275401", "TEMU 6275401")


def test_with_leading_trailing_spaces():
    """Пробелы по краям убираются."""
    result = normalize_container_number("  TEMU6275401  ")
    assert result == ("TEMU6275401", "TEMU 6275401")


def test_invalid_too_short():
    """Слишком короткий — None."""
    assert normalize_container_number("TEM625") is None


def test_invalid_wrong_format():
    """Цифры перед буквами — None."""
    assert normalize_container_number("1234TEMU567") is None


def test_invalid_empty():
    """Пустая строка — None."""
    assert normalize_container_number("") is None


def test_invalid_only_letters():
    """Только буквы — None."""
    assert normalize_container_number("TEMUABCDEFG") is None


def test_invalid_only_digits():
    """Только цифры — None."""
    assert normalize_container_number("12345678901") is None
