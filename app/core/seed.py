"""Инициализация тарифов: вызывается при старте приложения.

Добавление идемпотентно: повторный вызов не создаёт дубликатов.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff import Tariff

# Тарифы из ТЗ: (title, price), цена в копейках. Единственный источник данных.
TARIFFS: tuple[tuple[str, int], ...] = (
    ("basic", 990_000),
    ("standard", 1_990_000),
    ("premium", 2_990_000),
)


async def seed_tariffs(session: AsyncSession) -> None:
    """Добавляет тарифы, которых ещё нет в таблице ``tariffs``."""
    existing: set[str] = set(
        (await session.execute(select(Tariff.title))).scalars()
    )
    for title, price in TARIFFS:
        if title not in existing:
            session.add(Tariff(title=title, price=price))
    await session.commit()
