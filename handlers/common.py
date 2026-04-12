import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message

from db import upsert_user
from keyboards import BTN_CANCEL, main_menu

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = await upsert_user(message.from_user.id)
    is_admin = role == "admin"
    logger.info("/start: user=%s role=%s", message.from_user.id, role)
    await message.answer(
        f"👋 Добро пожаловать в систему учёта контейнеров!\n"
        f"Твоя роль: <b>{'Администратор' if is_admin else 'Оператор'}</b>",
        reply_markup=main_menu(is_admin),
    )


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    role = await upsert_user(message.from_user.id)
    await message.answer("Действие отменено.", reply_markup=main_menu(role == "admin"))


# Обработчик устаревших/неизвестных callback-кнопок:
# регистрируется последним (см. handlers/__init__.py).
fallback_router = Router()
fallback_router.message.filter(F.chat.type == "private")


@fallback_router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    """Отвечает на любой нераспознанный callback — убирает 'часики' у клиента."""
    logger.info("Устаревший callback от user=%s: %s", callback.from_user.id, callback.data)
    await callback.answer("Кнопка устарела. Открой меню заново.", show_alert=False)


@fallback_router.errors()
async def global_error_handler(event: ErrorEvent) -> None:
    """Глобальный обработчик исключений: пишет traceback в лог и сообщает пользователю."""
    logger.exception("Необработанное исключение: %s", event.exception)
    # Пытаемся вежливо уведомить пользователя, если есть контекст сообщения/callback
    try:
        if event.update.message:
            await event.update.message.answer(
                "⚠️ Произошла внутренняя ошибка. Попробуй ещё раз или напиши /start."
            )
        elif event.update.callback_query and event.update.callback_query.message:
            await event.update.callback_query.message.answer(
                "⚠️ Произошла внутренняя ошибка. Попробуй ещё раз или напиши /start."
            )
            await event.update.callback_query.answer()
    except Exception:
        # Если и уведомление упало — уже ничего не поделать, всё в логах
        logger.exception("Не удалось уведомить пользователя об ошибке")
