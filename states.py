from aiogram.fsm.state import State, StatesGroup


class RegisterContainer(StatesGroup):
    """Регистрация нового контейнера."""
    waiting_for_company = State()
    waiting_for_arrival_date = State()
    waiting_for_manual_date = State()
    waiting_for_type = State()


class EditContainerNumber(StatesGroup):
    """Изменение номера контейнера."""
    waiting_for_number = State()


class ContainerDepart(StatesGroup):
    """Поток выбора даты вывоза контейнера.

    Используется и для первичного вывоза (mode='depart'), и для
    редактирования уже существующей даты (mode='edit'). Режим хранится
    в FSM-данных вместе с container_id.
    """
    waiting_for_departure_date = State()
    waiting_for_manual_date = State()


class EditCompanyEntry(StatesGroup):
    """Изменение стоимости входа компании."""
    waiting_for_value = State()


class EditCompanyFreeDays(StatesGroup):
    """Изменение количества бесплатных дней компании."""
    waiting_for_value = State()


class EditCompanyStorageRate(StatesGroup):
    """Изменение ставки платного хранения компании."""
    waiting_for_value = State()


class EditCompanyStoragePeriod(StatesGroup):
    """Изменение периода начисления хранения компании."""
    waiting_for_value = State()


class EditCompanyName(StatesGroup):
    """Изменение названия компании."""
    waiting_for_name = State()


class EditDefaultEntry(StatesGroup):
    """Изменение стандартной стоимости входа."""
    waiting_for_value = State()


class EditDefaultFreeDays(StatesGroup):
    """Изменение стандартного количества бесплатных дней."""
    waiting_for_value = State()


class EditDefaultStorageRate(StatesGroup):
    """Изменение стандартной ставки хранения."""
    waiting_for_value = State()


class EditDefaultStoragePeriod(StatesGroup):
    """Изменение стандартного периода начисления."""
    waiting_for_value = State()


class ContainerSection(StatesGroup):
    """Пользователь находится в разделе контейнеров.

    Поток:
    - menu — главный экран раздела (2 кнопки: добавить/найти по типу);
    - search_by_type — экран выбора типа и список найденных контейнеров
      выбранного типа (остаётся в этом состоянии после клика по типу).
    """
    menu = State()
    search_by_type = State()
    card = State()
    choosing_type = State()
    choosing_company = State()
    confirming_delete = State()


class ReportsMenu(StatesGroup):
    """Пользователь в разделе отчётов.

    Поток: выбор типа отчёта → выбор режима (все/одна компания) →
    (опционально) выбор компании → генерация файла и сброс FSM.
    """
    choosing_type = State()
    choosing_scope = State()
    choosing_company = State()


class SettingsSection(StatesGroup):
    """Пользователь в разделе настроек."""
    menu = State()


class CompaniesSection(StatesGroup):
    """Пользователь в разделе компаний."""
    list = State()
    card = State()
    confirming_delete = State()
    adding_name = State()


class UsersSection(StatesGroup):
    """Пользователь в подразделе «Пользователи и роли»."""
    list = State()
    role_edit = State()


class DefaultsSection(StatesGroup):
    """Пользователь в подразделе «Стандартные тарифы»."""
    view = State()
