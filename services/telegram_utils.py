"""Утилиты работы с Telegram API.

Лимит длины сообщения в Telegram — 4096 символов. Без разбивки длинного
текста (например, список из сотни контейнеров в карточке компании) бот
падает с TelegramBadRequest: message is too long. Здесь функции, которые
разбивают текст и отправляют его кусками.
"""
import logging

from aiogram.types import Message

logger = logging.getLogger(__name__)

# Буфер на 96 символов: Telegram считает по символам Unicode, HTML-теги
# и экранирование могут чуть увеличить реальную длину.
_MAX_MESSAGE_LENGTH = 4000


def split_text(text: str, max_len: int = _MAX_MESSAGE_LENGTH) -> list[str]:
    """Режет длинный текст на куски ≤ max_len, по переносам строки.

    Если одна строка сама по себе длиннее max_len (редкий случай —
    огромный блок без \\n) — режем её пополам, чтоб не зависнуть в
    бесконечном цикле.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # Патологический случай: одна строка больше лимита
        while len(line) > max_len:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_len])
            line = line[max_len:]

        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks


async def send_long(
    message: Message,
    text: str,
    reply_markup=None,
) -> None:
    """Отправляет текст, разбивая на куски если длиннее лимита.

    reply_markup прикрепляется только к ПОСЛЕДНЕМУ сообщению — иначе
    клавиатура продублировалась бы на каждый чанк и это выглядит коряво.
    Для однострочных сообщений (≤ лимита) — обычный message.answer.
    """
    chunks = split_text(text)
    last_idx = len(chunks) - 1
    for i, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=reply_markup if i == last_idx else None,
        )
