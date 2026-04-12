"""Сценарии нового FSM ContainerDepart (без Telegram).

Создаём тестовый контейнер в БД, прогоняем хэндлеры напрямую, в конце
удаляем тестовую запись. Никаких внешних эффектов в реальных данных.
"""
import asyncio
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import db
db._DB_PATH = "container.db"

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

import handlers.containers as h
from states import ContainerDepart, ContainerSection
from keyboards.containers import (
    BTN_DEPART_TODAY, BTN_DEPART_MANUAL, BTN_DEPART_CANCEL,
)


# Заглушаем перерисовку карточки.
async def _fake_send_card(message, container, state=None, source=None):
    message.captured.append(
        ("CARD", container["display_number"], container["status"],
         container["departure_date"])
    )
    if state is not None:
        await state.set_state(ContainerSection.card)
        await state.update_data(container_id=container["id"])


h._send_container_card = _fake_send_card


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.captured = []

    async def answer(self, text, reply_markup=None):
        kb = None
        if reply_markup is not None and hasattr(reply_markup, "keyboard"):
            kb = tuple(
                tuple(b.text for b in row) for row in reply_markup.keyboard
            )
        self.captured.append((text, kb))


storage = MemoryStorage()


def make_state(uid):
    key = StorageKey(bot_id=1, chat_id=uid, user_id=uid)
    return FSMContext(storage=storage, key=key)


def setup_container():
    conn = sqlite3.connect("container.db")
    arrival = (datetime.now() - timedelta(days=10)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur = conn.execute(
        "INSERT INTO containers (number, display_number, company_id, "
        "status, type, registered_at, arrival_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("TESTSMOKE9991", "TEST 9999991", 1, "on_terminal", "20HQ",
         arrival, arrival),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid, arrival


def cleanup_container(cid):
    conn = sqlite3.connect("container.db")
    conn.execute("DELETE FROM containers WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def get_status_and_dep(cid):
    conn = sqlite3.connect("container.db")
    row = conn.execute(
        "SELECT status, departure_date FROM containers WHERE id=?", (cid,)
    ).fetchone()
    conn.close()
    return row


async def main():
    cid, arrival_str = setup_container()
    print(f"created test container id={cid}, arrival={arrival_str}")
    try:
        # 1. card_depart_start
        state = make_state(100)
        await state.set_state(ContainerSection.card)
        await state.update_data(container_id=cid)
        msg = FakeMessage("BTN_DEPART")
        await h.card_depart_start(msg, state)
        cur = await state.get_state()
        print(f"\n[1] state={cur}")
        for t, kb in msg.captured:
            print(f"    out: {t} kb={kb}")
        assert cur == ContainerDepart.waiting_for_departure_date.state
        assert msg.captured[0][0].startswith("📤 Вывоз контейнера")
        expected_kb = (
            ("📅 Сегодня",), ("✏️ Ввести дату вручную",), ("◀ Отмена",)
        )
        assert msg.captured[1][1] == expected_kb

        # 2. manual → невалидный формат
        msg = FakeMessage(BTN_DEPART_MANUAL)
        await h.depart_choose_manual(msg, state)
        cur = await state.get_state()
        print(f"\n[2a] state={cur}")
        assert cur == ContainerDepart.waiting_for_manual_date.state

        msg = FakeMessage("ololo")
        await h.depart_manual_input(msg, state)
        cur = await state.get_state()
        print(f"[2b] msg={msg.captured[-1][0]}, state={cur}")
        assert "Неверный формат" in msg.captured[-1][0]
        assert cur == ContainerDepart.waiting_for_manual_date.state
        assert get_status_and_dep(cid) == ("on_terminal", None)

        # 3. дата в будущем
        future = (datetime.now() + timedelta(days=2)).strftime("%d.%m.%Y")
        msg = FakeMessage(future)
        await h.depart_manual_input(msg, state)
        print(f"[3] future={future} -> {msg.captured[-1][0]}")
        assert "не может быть в будущем" in msg.captured[-1][0]
        assert get_status_and_dep(cid) == ("on_terminal", None)

        # 4. дата раньше прибытия
        before = (datetime.now() - timedelta(days=20)).strftime("%d.%m.%Y")
        msg = FakeMessage(before)
        await h.depart_manual_input(msg, state)
        print(f"[4] before={before} -> {msg.captured[-1][0]}")
        assert "раньше даты прибытия" in msg.captured[-1][0]
        assert get_status_and_dep(cid) == ("on_terminal", None)

        # 5. валидная дата (mode=depart, через manual)
        valid_dt = datetime.now() - timedelta(days=2)
        valid = valid_dt.strftime("%d.%m.%Y")
        msg = FakeMessage(valid)
        await h.depart_manual_input(msg, state)
        cur = await state.get_state()
        st, dep = get_status_and_dep(cid)
        print(f"\n[5] valid={valid} -> status={st} dep={dep} state={cur}")
        assert st == "departed"
        assert dep.startswith(valid_dt.strftime("%Y-%m-%d"))
        assert any(
            isinstance(c[0], str) and "вывезен" in c[0]
            for c in msg.captured
        )
        assert any(c[0] == "CARD" for c in msg.captured)
        assert cur == ContainerSection.card.state

        # 6. cancel на select-подэкране
        conn = sqlite3.connect("container.db")
        conn.execute(
            "UPDATE containers SET status='on_terminal', "
            "departure_date=NULL WHERE id=?",
            (cid,),
        )
        conn.commit()
        conn.close()

        state = make_state(101)
        await state.set_state(ContainerSection.card)
        await state.update_data(container_id=cid)
        msg = FakeMessage("BTN_DEPART")
        await h.card_depart_start(msg, state)
        msg = FakeMessage(BTN_DEPART_CANCEL)
        await h.depart_cancel_select(msg, state)
        cur = await state.get_state()
        print(
            f"\n[6] cancel on select -> state={cur}, "
            f"status={get_status_and_dep(cid)}"
        )
        assert get_status_and_dep(cid) == ("on_terminal", None)
        assert cur == ContainerSection.card.state

        # 7. cancel на manual-подэкране
        msg = FakeMessage("BTN_DEPART")
        await h.card_depart_start(msg, state)
        msg = FakeMessage(BTN_DEPART_MANUAL)
        await h.depart_choose_manual(msg, state)
        msg = FakeMessage(BTN_DEPART_CANCEL)
        await h.depart_cancel_manual(msg, state)
        cur = await state.get_state()
        print(
            f"[7] cancel on manual -> state={cur}, "
            f"status={get_status_and_dep(cid)}"
        )
        assert get_status_and_dep(cid) == ("on_terminal", None)
        assert cur == ContainerSection.card.state

        # 8. edit-mode: сначала вывезем "Сегодня"
        state = make_state(102)
        await state.set_state(ContainerSection.card)
        await state.update_data(container_id=cid)
        msg = FakeMessage("BTN_DEPART")
        await h.card_depart_start(msg, state)
        msg = FakeMessage(BTN_DEPART_TODAY)
        await h.depart_today(msg, state)
        st, dep = get_status_and_dep(cid)
        print(f"\n[8a] depart today -> status={st} dep={dep}")
        assert st == "departed"

        await state.set_state(ContainerSection.card)
        await state.update_data(container_id=cid)
        msg = FakeMessage("EDIT")
        await h.card_edit_departure_date(msg, state)
        cur = await state.get_state()
        print(f"[8b] edit_departure_date entered, state={cur}")
        print(f"    header: {msg.captured[0][0]}")
        assert cur == ContainerDepart.waiting_for_departure_date.state
        assert "Изменение даты вывоза" in msg.captured[0][0]
        assert "Текущая дата вывоза" in msg.captured[0][0]

        # 9. edit + Сегодня — статус остаётся departed, текст confirmation
        # должен быть «Дата вывоза изменена…»
        msg = FakeMessage(BTN_DEPART_TODAY)
        await h.depart_today(msg, state)
        st, dep = get_status_and_dep(cid)
        print(f"\n[9] edit-today -> status={st} dep={dep}")
        assert st == "departed"
        assert any(
            isinstance(c[0], str) and "Дата вывоза изменена" in c[0]
            for c in msg.captured
        )

        # 10. fallback на select-подэкране — текст-подсказка
        msg = FakeMessage("случайный текст")
        await h.depart_select_fallback(msg)
        print(f"\n[10] fallback -> {msg.captured[-1][0]}")
        assert "Выберите вариант" in msg.captured[-1][0]

        print("\n=== ВСЕ СЦЕНАРИИ OK ===")
    finally:
        cleanup_container(cid)
        print(f"cleanup: deleted test container id={cid}")


if __name__ == "__main__":
    asyncio.run(main())
