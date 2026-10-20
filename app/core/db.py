"""Асинхронные подключения к PostgreSQL через SQLAlchemy 2.x и asyncpg."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Подключение основной части приложения.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


def create_test_session_factory() -> tuple[
    AsyncEngine, async_sessionmaker[AsyncSession]
]:
    """Создаёт отдельное подключение и фабрику сессий для тестовой БД."""
    test_engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        echo=False,
    )
    test_session_local = async_sessionmaker(
        test_engine,
        expire_on_commit=False,
    )
    return test_engine, test_session_local


async def check_connection() -> None:
    """Минимальная проверка соединения с основной БД (SELECT 1).

    Вызывается один раз при старте приложения; при недоступности БД
    старт завершается ошибкой.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: сессия основной БД на один запрос."""
    async with SessionLocal() as session:
        yield session
