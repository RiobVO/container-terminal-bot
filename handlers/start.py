"""Хэндлеры команд /start, /help, /menu, /cancel, ◀ Назад, fallback."""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message

from config import load_config
from db.users import upsert_user
from keyboards.main import BTN_BACK, main_menu

logger = logging.getLogger(__name__)
router = Router()

_cfg = load_config()

_NO_ACCESS = "⛔ У вас нет доступа. Обратитесь к администратору."

_HELP_TEXT = (
    "ℹ️ Как пользоваться ботом:\n\n"
    "- Чтобы найти контейнер — перейдите в 📦 Контейнеры и введите "
    "номер текстом (например: OLSO 1234567).\n"
    "- Чтобы зарегистрировать новый контейнер — введите номер, "
    "которого ещё нет в системе.\n"
    "- Чтобы сформировать отчёт — перейдите в 📊 Отчёты.\n"
    "- /menu — вернуться в главное меню.\n"
    "- /cancel — отменить текущее действие."
)


async def _send_main_menu(message: Message, role: str, text: str) -> None:
    """Шлёт текст + reply-меню по роли. role='none' → отказ доступа."""
    if role == "none":
        await message.answer(_NO_ACCESS)
        return
    await message.answer(text, reply_markup=main_menu(role))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Обработчик /start: апсерт юзера, приветствие, главное меню по роли."""
    await state.clear()
    user = message.from_user
    role = await upsert_user(
        tg_id=user.id,
        username=user.username,
        full_name=user.full_name,
        admin_ids=_cfg.admin_ids,
    )
    logger.info("/start: user=%s role=%s", user.id, role)

    await _send_main_menu(
        message,
        role,
        "👋 Добро пожаловать! Это бот учёта контейнеров терминала. "
        "Выберите раздел в меню ниже.",
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    """Краткая справка. FSM сбрасывается, клавиатура не трогается."""
    await state.clear()
    await message.answer(_HELP_TEXT)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, state: FSMContext, role: str
) -> None:
    """Сбросить FSM и показать главное меню по роли."""
    await state.clear()
    await _send_main_menu(message, role, "Главное меню")


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, state: FSMContext, role: str
) -> None:
    """Отменить текущее действие и вернуть пользователя в главное меню."""
    await state.clear()
    await _send_main_menu(
        message, role, "❌ Действие отменено. Вы в главном меню."
    )


# ---------------------------------------------------------------------------
# Fallback-роутер (подключается последним в __init__.py)
# ---------------------------------------------------------------------------

fallback_router = Router()


@fallback_router.message(F.text == BTN_BACK)
async def fallback_back(message: Message, state: FSMContext, role: str) -> None:
    """◀ Назад из любого состояния → главное меню."""
    await state.clear()
    if role == "none":
        await message.answer("⛔ У вас нет доступа. Обратитесь к администратору.")
        return
    await message.answer("Главное меню", reply_markup=main_menu(role))


@fallback_router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    """Устаревший callback."""
    logger.info("Устаревший callback: user=%s data=%s", callback.from_user.id, callback.data)
    await callback.answer("Кнопка устарела. Нажми /start.", show_alert=False)


@fallback_router.errors()
async def global_error_handler(event: ErrorEvent) -> None:
    """Глобальный обработчик исключений."""
    logger.exception("Необработанное исключение: %s", event.exception)
    try:
        if event.update.message:
            await event.update.message.answer(
                "⚠️ Произошла ошибка. Попробуй /start."
            )
        elif event.update.callback_query and event.update.callback_query.message:
            await event.update.callback_query.message.answer(
                "⚠️ Произошла ошибка. Попробуй /start."
            )
            await event.update.callback_query.answer()
    except Exception:
        logger.exception("Не удалось уведомить об ошибке")
