"""Маскировка токена бота в логах.

Фильтр переписывает msg/args записи до форматирования, поэтому токен
не утекает ни через текст сообщения, ни через %-подстановку аргументов.
"""
import logging
import re

MASK = "***TOKEN***"

# Общий вид Telegram-токена: числовой id бота, двоеточие, секрет
_TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")


class TokenMaskingFilter(logging.Filter):
    """Заменяет значение BOT_TOKEN и токеноподобные строки на ***TOKEN***."""

    def __init__(self, token: str | None = None) -> None:
        super().__init__()
        self._token = token or ""

    def _mask(self, text: str) -> str:
        """Сначала точное значение токена, затем общий паттерн."""
        if self._token:
            text = text.replace(self._token, MASK)
        return _TOKEN_RE.sub(MASK, text)

    def filter(self, record: logging.LogRecord) -> bool:
        # msg бывает не строкой (логируют объекты/исключения) — такие не трогаем
        if isinstance(record.msg, str):
            record.msg = self._mask(record.msg)

        # args: либо tuple, либо dict (один mapping-аргумент); маскируем только строки
        if isinstance(record.args, dict):
            record.args = {
                key: self._mask(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        elif record.args:
            record.args = tuple(
                self._mask(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )

        return True
