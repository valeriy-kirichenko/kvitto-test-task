"""S3: модели, миграции и идемпотентный seed тарифов."""

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seed import TARIFFS, seed_tariffs
from app.models.payment import Payment
from app.models.tariff import Tariff


async def test_tariffs_seeded_with_expected_prices(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """В БД есть три тарифа из ТЗ с ценами в копейках."""
    rows = (await db.execute(select(Tariff.title, Tariff.price))).all()
    assert dict(rows) == dict(TARIFFS)


async def test_seed_is_idempotent(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Повторный вызов seed не создаёт дубликаты тарифов."""
    await seed_tariffs(db)
    await seed_tariffs(db)
    result = await db.execute(select(func.count()).select_from(Tariff))
    assert result.scalar_one() == 3


async def test_payment_model_roundtrip(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Модель Payment хранит все поля API; schedule — список целых (JSONB).

    Строка удаляется после проверки, чтобы не копиться в тестовой БД.
    """
    basic_id = (
        await db.execute(select(Tariff.id).where(Tariff.title == "basic"))
    ).scalar_one()
    payment = Payment(
        status="pending",
        tariff_id=basic_id,
        amount=891_000,
        discount=99_000,
        method="installment",
        installment_months=3,
        schedule=[297_001, 297_000, 297_000],
        email="user@example.com",
        idempotency_key="key-roundtrip-test",
    )
    db.add(payment)
    await db.commit()

    row = (
        await db.execute(select(Payment).where(Payment.id == payment.id))
    ).scalar_one()
    result = row.schedule
    assert row.status == "pending"
    assert row.installment_months == 3
    await db.delete(row)
    await db.commit()
    assert result == [297_001, 297_000, 297_000]
