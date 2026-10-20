"""S3: модели, миграции и идемпотентный seed тарифов."""

from sqlalchemy import func, select
from starlette.testclient import TestClient

from app.core.seed import TARIFFS, seed_tariffs
from app.models.payment import Payment
from app.models.tariff import Tariff


def test_tariffs_seeded_with_expected_prices(client: TestClient, db) -> None:
    """В БД есть три тарифа из ТЗ с ценами в копейках."""
    async def _query() -> dict[str, int]:
        rows = (await db.execute(select(Tariff.title, Tariff.price))).all()
        return dict(rows)

    assert client.portal.call(_query) == dict(TARIFFS)


def test_seed_is_idempotent(client: TestClient, db) -> None:
    """Повторный вызов seed не создаёт дубликаты тарифов."""
    async def _run_twice() -> int:
        await seed_tariffs(db)
        await seed_tariffs(db)
        result = await db.execute(select(func.count()).select_from(Tariff))
        return result.scalar_one()

    assert client.portal.call(_run_twice) == 3


def test_payment_model_roundtrip(client: TestClient, db) -> None:
    """Модель Payment хранит все поля API; schedule — список целых (JSONB).

    Строка удаляется после проверки, чтобы не копиться в тестовой БД.
    """
    async def _do() -> list[int]:
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
        return result

    assert client.portal.call(_do) == [297_001, 297_000, 297_000]
