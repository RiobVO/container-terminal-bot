"""Хэндлеры раздела «Настройки» — reply-first.

Гибкая модель стандартных тарифов: 4 параметра в global_settings —
default_entry_fee, default_free_days, default_storage_rate,
default_storage_period_days.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import load_config
from db import users as db_users
from db.settings import get_all_settings, set_setting
from keyboards.main import BTN_BACK, BTN_SETTINGS, main_menu
from keyboards.settings import (
    BTN_CANCEL_BACK,
    BTN_DEF_ENTRY,
    BTN_DEF_FREE,
    BTN_DEF_STORAGE_PERIOD,
    BTN_DEF_STORAGE_RATE,
    BTN_ROLE_FULL,
    BTN_ROLE_NONE,
    BTN_ROLE_REPORTS,
    BTN_SET_DEFAULTS,
    BTN_SET_USERS,
    ROLE_ICONS,
    ROLE_NAMES,
    default_edit_reply_kb,
    defaults_reply_kb,
    settings_reply_kb,
    user_role_reply_kb,
    users_list_reply_kb,
)
from states import (
    DefaultsSection,
    EditDefaultEntry,
    EditDefaultFreeDays,
    EditDefaultStoragePeriod,
    EditDefaultStorageRate,
    SettingsSection,
    UsersSection,
)

logger = logging.getLogger(__name__)
router = Router()

_cfg = load_config()


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------


@router.message(F.text == BTN_SETTINGS)
async def settings_menu(
    message: Message, state: FSMContext, role: str
) -> None:
    if role != "full":
        await message.answer("⛔ У вас нет доступа. Обратитесь к администратору.")
        return
    await state.set_state(SettingsSection.menu)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите действие:",
        reply_markup=settings_reply_kb(),
    )


@router.message(SettingsSection.menu, F.text == BTN_BACK)
async def settings_back(
    message: Message, state: FSMContext, role: str
) -> None:
    await state.clear()
    await message.answer("Главное меню", reply_markup=main_menu(role))


# ---------------------------------------------------------------------------
# Пользователи и роли
# ---------------------------------------------------------------------------


@router.message(SettingsSection.menu, F.text == BTN_SET_USERS)
async def users_menu_from_settings(
    message: Message, state: FSMContext
) -> None:
    await _show_users(message, state)


async def _show_users(message: Message, state: FSMContext) -> None:
    users = await db_users.list_users()
    if not users:
        await state.set_state(UsersSection.list)
        await state.update_data(users_map={})
        await message.answer(
            "👥 <b>Пользователи и роли</b>\n\nНет пользователей.",
            reply_markup=users_list_reply_kb([], _cfg.admin_ids)[0],
        )
        return

    lines: list[str] = []
    for u in users:
        icon = ROLE_ICONS.get(u["role"], "❓")
        name = u["full_name"] or "—"
        username = f"@{u['username']}" if u["username"] else "—"
        protected = " 🔒" if u["tg_id"] in _cfg.admin_ids else ""
        lines.append(
            f"{icon} <b>{name}</b>{protected}\n"
            f"   {username} | ID: <code>{u['tg_id']}</code>\n"
            f"   Роль: {ROLE_NAMES.get(u['role'], u['role'])}"
        )
    text = "👥 <b>Пользователи и роли</b>\n\n" + "\n\n".join(lines)

    kb, mapping = users_list_reply_kb(users, _cfg.admin_ids)
    await state.set_state(UsersSection.list)
    await state.update_data(users_map=mapping)
    await message.answer(text, reply_markup=kb)


@router.message(UsersSection.list, F.text == BTN_BACK)
async def users_back(message: Message, state: FSMContext) -> None:
    await state.set_state(SettingsSection.menu)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите действие:",
        reply_markup=settings_reply_kb(),
    )


@router.message(UsersSection.list, F.text == BTN_SET_DEFAULTS)
async def users_to_defaults(message: Message, state: FSMContext) -> None:
    await _show_defaults(message, state)


@router.message(UsersSection.list)
async def users_pick(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    mapping: dict[str, int] = data.get("users_map", {})
    if text not in mapping:
        return

    tg_id = mapping[text]
    user = await db_users.get_user(tg_id)
    if not user:
        await message.answer("⚠️ Пользователь не найден.")
        return

    if tg_id in _cfg.admin_ids:
        await message.answer("🔒 Защищённый админ — роль изменить нельзя.")
        return

    name = user["full_name"] or "—"
    await state.set_state(UsersSection.role_edit)
    await state.update_data(target_tg_id=tg_id)
    await message.answer(
        f"👤 <b>{name}</b>\n"
        f"ID: <code>{tg_id}</code>\n\n"
        f"Текущая роль: {ROLE_NAMES.get(user['role'], user['role'])}\n\n"
        "Выберите новую роль:",
        reply_markup=user_role_reply_kb(),
    )


_ROLE_BY_BTN = {
    BTN_ROLE_FULL: "full",
    BTN_ROLE_REPORTS: "reports_only",
    BTN_ROLE_NONE: "none",
}


@router.message(UsersSection.role_edit, F.text == BTN_CANCEL_BACK)
async def role_cancel(message: Message, state: FSMContext) -> None:
    await _show_users(message, state)


@router.message(UsersSection.role_edit, F.text.in_(_ROLE_BY_BTN.keys()))
async def role_set(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tg_id = data.get("target_tg_id")
    if tg_id is None:
        return

    if tg_id in _cfg.admin_ids:
        await message.answer("🔒 Защищённый админ — роль изменить нельзя.")
        await _show_users(message, state)
        return

    new_role = _ROLE_BY_BTN[message.text]
    await db_users.set_role(tg_id, new_role)
    logger.info(
        "Роль: tg_id=%s -> %s (by %s)",
        tg_id, new_role, message.from_user.id,
    )
    await message.answer("✅ Роль обновлена.")
    await _show_users(message, state)


@router.message(UsersSection.role_edit)
async def role_fallback(message: Message) -> None:
    return


# ---------------------------------------------------------------------------
# Стандартные тарифы
# ---------------------------------------------------------------------------


def _period_label(period_days: int) -> str:
    if period_days <= 1:
        return "ежедневный тариф"
    if period_days == 30:
        return "ежемесячный тариф"
    return f"каждые {period_days} дн."


@router.message(SettingsSection.menu, F.text == BTN_SET_DEFAULTS)
async def defaults_from_settings(
    message: Message, state: FSMContext
) -> None:
    await _show_defaults(message, state)


async def _show_defaults(message: Message, state: FSMContext) -> None:
    settings = await get_all_settings()
    entry = float(settings.get("default_entry_fee", 20.0))
    free = int(settings.get("default_free_days", 30))
    rate = float(settings.get("default_storage_rate", 20.0))
    period = int(settings.get("default_storage_period_days", 30))

    text = (
        "💰 <b>Стандартные тарифы</b>\n\n"
        f"💵 Стоимость входа: {entry} $\n"
        f"🆓 Бесплатных дней: {free}\n"
        f"💰 Ставка хранения: {rate} $ за {period} дн.\n"
        f"📅 Период начисления: {period} дн. ({_period_label(period)})\n\n"
        "Выберите, что изменить:"
    )
    await state.set_state(DefaultsSection.view)
    await message.answer(text, reply_markup=defaults_reply_kb())


@router.message(DefaultsSection.view, F.text == BTN_BACK)
async def defaults_back(message: Message, state: FSMContext) -> None:
    await state.set_state(SettingsSection.menu)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите действие:",
        reply_markup=settings_reply_kb(),
    )


@router.message(DefaultsSection.view, F.text == BTN_DEF_ENTRY)
async def def_edit_entry(message: Message, state: FSMContext) -> None:
    settings = await get_all_settings()
    current = float(settings.get("default_entry_fee", 20.0))
    await state.set_state(EditDefaultEntry.waiting_for_value)
    await message.answer(
        f"💵 Текущая стандартная стоимость входа: <b>{current} $</b>\n\n"
        "Введите новое значение (число ≥ 0):",
        reply_markup=default_edit_reply_kb(),
    )


@router.message(DefaultsSection.view, F.text == BTN_DEF_FREE)
async def def_edit_free(message: Message, state: FSMContext) -> None:
    settings = await get_all_settings()
    current = int(settings.get("default_free_days", 30))
    await state.set_state(EditDefaultFreeDays.waiting_for_value)
    await message.answer(
        f"🆓 Текущее количество бесплатных дней: <b>{current}</b>\n\n"
        "Введите новое значение (целое число ≥ 0):",
        reply_markup=default_edit_reply_kb(),
    )


@router.message(DefaultsSection.view, F.text == BTN_DEF_STORAGE_RATE)
async def def_edit_storage_rate(
    message: Message, state: FSMContext
) -> None:
    settings = await get_all_settings()
    current = float(settings.get("default_storage_rate", 20.0))
    await state.set_state(EditDefaultStorageRate.waiting_for_value)
    await message.answer(
        f"💰 Текущая ставка хранения: <b>{current} $</b>\n\n"
        "Введите новое значение (число ≥ 0):",
        reply_markup=default_edit_reply_kb(),
    )


@router.message(DefaultsSection.view, F.text == BTN_DEF_STORAGE_PERIOD)
async def def_edit_storage_period(
    message: Message, state: FSMContext
) -> None:
    settings = await get_all_settings()
    current = int(settings.get("default_storage_period_days", 30))
    await state.set_state(EditDefaultStoragePeriod.waiting_for_value)
    await message.answer(
        f"📅 Текущий период начисления: <b>{current} дн.</b> "
        f"({_period_label(current)})\n\n"
        "Введите новое значение (целое число ≥ 1, "
        "1 = ежедневный, 30 = ежемесячный):",
        reply_markup=default_edit_reply_kb(),
    )


@router.message(DefaultsSection.view)
async def defaults_fallback(message: Message) -> None:
    return


# ---------------------------------------------------------------------------
# FSM ввода значений стандартных тарифов
# ---------------------------------------------------------------------------


@router.message(EditDefaultEntry.waiting_for_value, F.text == BTN_CANCEL_BACK)
async def def_entry_cancel(message: Message, state: FSMContext) -> None:
    await _show_defaults(message, state)


@router.message(EditDefaultEntry.waiting_for_value)
async def def_entry_value(message: Message, state: FSMContext) -> None:
    val = _parse_float(message.text)
    if val is None:
        await message.answer("❌ Введите число (например: 15 или 25.5)")
        return
    await set_setting("default_entry_fee", val)
    await message.answer(f"✅ Стандартная стоимость входа: <b>{val} $</b>")
    await _show_defaults(message, state)


@router.message(EditDefaultFreeDays.waiting_for_value, F.text == BTN_CANCEL_BACK)
async def def_free_cancel(message: Message, state: FSMContext) -> None:
    await _show_defaults(message, state)


@router.message(EditDefaultFreeDays.waiting_for_value)
async def def_free_value(message: Message, state: FSMContext) -> None:
    val = _parse_int_nonneg(message.text)
    if val is None:
        await message.answer("❌ Введите целое число ≥ 0")
        return
    await set_setting("default_free_days", float(val))
    await message.answer(f"✅ Бесплатных дней: <b>{val}</b>")
    await _show_defaults(message, state)


@router.message(
    EditDefaultStorageRate.waiting_for_value, F.text == BTN_CANCEL_BACK
)
async def def_rate_cancel(message: Message, state: FSMContext) -> None:
    await _show_defaults(message, state)


@router.message(EditDefaultStorageRate.waiting_for_value)
async def def_rate_value(message: Message, state: FSMContext) -> None:
    val = _parse_float(message.text)
    if val is None:
        await message.answer("❌ Введите число (например: 0.5 или 20)")
        return
    await set_setting("default_storage_rate", val)
    await message.answer(f"✅ Стандартная ставка хранения: <b>{val} $</b>")
    await _show_defaults(message, state)


@router.message(
    EditDefaultStoragePeriod.waiting_for_value, F.text == BTN_CANCEL_BACK
)
async def def_period_cancel(message: Message, state: FSMContext) -> None:
    await _show_defaults(message, state)


@router.message(EditDefaultStoragePeriod.waiting_for_value)
async def def_period_value(message: Message, state: FSMContext) -> None:
    val = _parse_int_positive(message.text)
    if val is None:
        await message.answer(
            "❌ Введите целое число ≥ 1 (1 = ежедневный, 30 = ежемесячный)"
        )
        return
    await set_setting("default_storage_period_days", float(val))
    await message.answer(
        f"✅ Стандартный период начисления: <b>{val} дн.</b> "
        f"({_period_label(val)})"
    )
    await _show_defaults(message, state)


# ---------------------------------------------------------------------------
# Парсеры
# ---------------------------------------------------------------------------


def _parse_float(text: str | None) -> float | None:
    try:
        v = float((text or "").strip().replace(",", "."))
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_int_nonneg(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 0 else None
    except ValueError:
        return None


def _parse_int_positive(text: str | None) -> int | None:
    try:
        v = int((text or "").strip())
        return v if v >= 1 else None
    except ValueError:
        return None
