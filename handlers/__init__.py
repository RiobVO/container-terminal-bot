from aiogram import Dispatcher

from handlers.start import fallback_router, router as start_router
from handlers.containers import router as containers_router
from handlers.register import router as register_router
from handlers.companies import router as companies_router
from handlers.reports import router as reports_router
from handlers.settings import router as settings_router
from handlers.report_callbacks import router as report_callbacks_router


def setup_routers(dp: Dispatcher) -> None:
    """Регистрирует все роутеры."""
    dp.include_router(start_router)
    dp.include_router(register_router)
    dp.include_router(containers_router)
    dp.include_router(companies_router)
    dp.include_router(reports_router)
    dp.include_router(settings_router)
    dp.include_router(report_callbacks_router)
    # Последним — fallback для ◀ Назад из любого состояния и устаревших callback
    dp.include_router(fallback_router)
