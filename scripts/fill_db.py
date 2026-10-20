"""Наполнение БД тестовыми данными.

Скрипт создаёт тестовые тарифы (те же, что в ``app.core.seed``) и набор
платежей, покрывающий все статусы (``pending``, ``succeeded``, ``failed``,
``refunded``), все способы оплаты (``card``, ``sbp``, ``installment``),
скидку по промокоду и графики рассрочки.

Повторный запуск не создаёт дубликатов:
- тарифы добавляются только если их ещё нет;
- платежи имеют уникальные ``idempotency_key`` (``test-seed-...``),
  повторная вставка с тем же ключом пропускается.

Запуск (из корня проекта):

    uv run python -m scripts.fill_db          # основная БД (DATABASE_URL)
    uv run python -m scripts.fill_db --test   # тестовая БД (TEST_DATABASE_URL)
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import SessionLocal, create_test_session_factory
from app.core.seed import seed_tariffs
from app.domain import installments, promo_discount
from app.models.payment import Payment
from app.models.tariff import Tariff

# Тестовые платежи: (тариф, способ, скидка по промокоду, срок рассрочки,
# статус, email, ключ идемпотентности).
# Суммы рассчитываются из цены тарифа, как в API: amount = price - discount.
TEST_PAYMENTS: tuple[dict, ...] = (
    {
        "tariff": "basic",
        "method": "card",
        "with_promo": False,
        "months": None,
        "status": "succeeded",
        "email": "seed-user-1@example.com",
        "idempotency_key": "test-seed-basic-card-succeeded",
    },
    {
        "tariff": "basic",
        "method": "sbp",
        "with_promo": True,
        "months": None,
        "status": "pending",
        "email": "seed-user-2@example.com",
        "idempotency_key": "test-seed-basic-sbp-pending",
    },
    {
        "tariff": "standard",
        "method": "installment",
        "with_promo": False,
        "months": 3,
        "status": "succeeded",
        "email": "seed-user-3@example.com",
        "idempotency_key": "test-seed-standard-installment-3-succeeded",
    },
    {
        "tariff": "standard",
        "method": "card",
        "with_promo": False,
        "months": None,
        "status": "failed",
        "email": "seed-user-4@example.com",
        "idempotency_key": "test-seed-standard-card-failed",
    },
    {
        "tariff": "premium",
        "method": "installment",
        "with_promo": True,
        "months": 6,
        "status": "refunded",
        "email": "seed-user-5@example.com",
        "idempotency_key": "test-seed-premium-installment-6-refunded",
    },
    {
        "tariff": "premium",
        "method": "sbp",
        "with_promo": False,
        "months": None,
        "status": "pending",
        "email": "seed-user-6@example.com",
        "idempotency_key": "test-seed-premium-sbp-pending",
    },
)


async def seed_payments(session: AsyncSession) -> tuple[int, int]:
    """Создаёт тестовые платежи; возвращает (создано, пропущено)."""
    titles = [spec["tariff"] for spec in TEST_PAYMENTS]
    tariff_rows = (
        (await session.execute(select(Tariff).where(Tariff.title.in_(titles)))).scalars().all()
    )
    # Значения сразу читаем в обычные данные: после rollback ORM-объекты
    # истекают, и повторный доступ к атрибутам вызовет ленивую загрузку.
    tariffs = {t.title: (t.id, t.price) for t in tariff_rows}

    created = 0
    skipped = 0
    for spec in TEST_PAYMENTS:
        tariff_id, tariff_price = tariffs.get(spec["tariff"], (None, None))
        if tariff_id is None:
            raise RuntimeError(f"Тариф {spec['tariff']!r} не найден в БД")

        discount = promo_discount(tariff_price) if spec["with_promo"] else 0
        amount = tariff_price - discount
        months = spec["months"]
        schedule = installments(amount, months) if spec["method"] == "installment" else None

        payment = Payment(
            status=spec["status"],
            tariff_id=tariff_id,
            amount=amount,
            discount=discount,
            method=spec["method"],
            installment_months=months,
            schedule=schedule,
            email=spec["email"],
            idempotency_key=spec.get("idempotency_key"),
        )
        session.add(payment)
        try:
            await session.commit()
        except IntegrityError:
            # Платёж с этим idempotency_key уже существует — дубликат пропущен.
            await session.rollback()
            skipped += 1
            continue
        created += 1
    return created, skipped


async def run(use_test_db: bool = False) -> None:
    # Для тестовой БД создаём отдельный движок и закрываем его по завершении;
    # для основной используем готовый движок из app.core.db.
    test_engine: AsyncEngine | None = None
    if use_test_db:
        test_engine, session_factory = create_test_session_factory()
    else:
        session_factory = SessionLocal

    try:
        async with session_factory() as session:
            await seed_tariffs(session)
            created, skipped = await seed_payments(session)
            print(f"Платежей создано: {created}, пропущено (уже существуют): {skipped}")
    finally:
        if test_engine is not None:
            await test_engine.dispose()


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--test",
        action="store_true",
        help="наполнять тестовую БД (TEST_DATABASE_URL) вместо основной",
    )
    args = parser.parse_args()
    asyncio.run(run(use_test_db=args.test))


if __name__ == "__main__":
    main()
