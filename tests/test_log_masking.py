"""Тесты services/log_masking.py: маскировка токена в msg и args."""
import io
import logging

from services.log_masking import MASK, TokenMaskingFilter

TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1"
WEIRD_TOKEN = "weird-token-without-standard-shape"  # не матчится общим паттерном


def _record(msg, args=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


def test_masks_exact_token_in_msg():
    """Точное значение BOT_TOKEN маскируется даже без стандартной формы."""
    f = TokenMaskingFilter(WEIRD_TOKEN)
    rec = _record(f"url https://api.tg/bot{WEIRD_TOKEN}/sendMessage")
    assert f.filter(rec) is True
    assert WEIRD_TOKEN not in rec.getMessage()
    assert MASK in rec.getMessage()


def test_masks_pattern_without_configured_token():
    """Общий паттерн \\d{6,}:[...]{30,} ловится и без заданного токена."""
    f = TokenMaskingFilter()
    rec = _record(f"leaked {TOKEN} here")
    f.filter(rec)
    assert TOKEN not in rec.getMessage()
    assert MASK in rec.getMessage()


def test_masks_token_in_tuple_args():
    """Токен в %-аргументах маскируется до подстановки."""
    f = TokenMaskingFilter(TOKEN)
    rec = _record("token=%s attempt=%d", (TOKEN, 2))
    f.filter(rec)
    assert rec.getMessage() == f"token={MASK} attempt=2"


def test_masks_token_in_dict_args():
    """args бывает dict (один mapping-аргумент) — строки маскируются, числа целы."""
    f = TokenMaskingFilter(TOKEN)
    rec = _record("token=%(tok)s id=%(id)d", {"tok": TOKEN, "id": 5})
    f.filter(rec)
    assert rec.getMessage() == f"token={MASK} id=5"


def test_non_string_msg_untouched():
    """msg-объект (не строка) не модифицируется и не роняет фильтр."""
    payload = ValueError("boom")
    f = TokenMaskingFilter(TOKEN)
    rec = _record(payload)
    assert f.filter(rec) is True
    assert rec.msg is payload


def test_empty_args_untouched():
    """Пустые args не трогаются."""
    f = TokenMaskingFilter(TOKEN)
    rec = _record("plain message")
    f.filter(rec)
    assert rec.args is None


def test_clean_message_unchanged():
    """Сообщение без токена остаётся как есть."""
    f = TokenMaskingFilter(TOKEN)
    rec = _record("обычное сообщение 42:abc")
    f.filter(rec)
    assert rec.getMessage() == "обычное сообщение 42:abc"


def test_end_to_end_handler_output():
    """Фильтр на хендлере: в отформатированном выводе токена нет."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(TokenMaskingFilter(TOKEN))
    log = logging.getLogger("test_log_masking_e2e")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("start with %s", TOKEN)
    finally:
        log.removeHandler(handler)

    out = stream.getvalue()
    assert TOKEN not in out
    assert f"start with {MASK}" in out
