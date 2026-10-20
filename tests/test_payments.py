from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_asyncio import fixture
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import installments
from app.models.payment import Payment
from app.models.tariff import Tariff

EMAIL = "buyer@example.com"
RESPONSE_FIELDS = {
    "id",
    "status",
    "tariff_id",
    "amount",
    "discount",
    "method",
    "installment_months",
    "schedule",
    "email",
    "created_at",
}


@fixture(autouse=True)
async def clean_payments(db: AsyncSession) -> AsyncIterator[None]:
    """Удаляет платежи перед каждым тестом — тесты не зависят от порядка запуска."""
    await db.execute(delete(Payment))
    await db.commit()
    yield


async def _tariff_id(db: AsyncSession, title: str) -> int:
    result = await db.execute(select(Tariff.id).where(Tariff.title == title))
    return result.scalar_one()


async def _count_by_key(db: AsyncSession, key: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Payment).where(Payment.idempotency_key == key)
    )
    return result.scalar_one()


async def _count_all(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(Payment))
    return result.scalar_one()


async def test_create_payment_without_discount(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Без промокода: ``amount`` равна цене тарифа, ``discount`` — 0."""
    tariff_id = await _tariff_id(db, "standard")  # 1 990 000
    response = await client.post(
        "/payments",
        json={"tariff_id": tariff_id, "email": EMAIL, "method": "card"},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["tariff_id"] == tariff_id
    assert body["amount"] == 1_990_000
    assert body["discount"] == 0
    assert body["status"] == "pending"
    assert body["method"] == "card"
    assert body["installment_months"] is None
    assert body["schedule"] is None
    assert body["email"] == EMAIL


@pytest.mark.parametrize("promo", ["KVITTO10", "kvitto10", "KvItTo10"])
async def test_create_payment_promo_discount_case_insensitive(
    promo: str, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Промокод в любом регистре: 10% скидки, итог — цена минус скидка."""
    tariff_id = await _tariff_id(db, "basic")  # 990 000
    response = await client.post(
        "/payments",
        json={"tariff_id": tariff_id, "email": EMAIL, "method": "sbp", "promo_code": promo},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["discount"] == 99_000
    assert body["amount"] == 891_000


@pytest.mark.parametrize("months", [3, 6, 12])
async def test_create_payment_installment_schedule(
    months: int, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """График рассрочки на 3/6/12 месяцев: длина = срок, сумма частей = сумма платежа."""
    tariff_id = await _tariff_id(db, "standard")  # 1 990 000
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariff_id,
            "email": EMAIL,
            "method": "installment",
            "installment_months": months,
        },
    )
    assert response.status_code == 201
    body = response.json()
    amount = body["amount"]
    schedule = body["schedule"]
    assert body["installment_months"] == months
    assert schedule == installments(amount, months)
    assert len(schedule) == months
    assert sum(schedule) == amount


async def test_create_payment_installment_schedule_split_exact(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Неравномерное деление: лишние копейки — в первые платежи, сумма без потерь.

    1 990 000 = 331 666 * 6 + 4 → 4 платежа по 331 667 и 2 по 331 666.
    """
    tariff_id = await _tariff_id(db, "standard")
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariff_id,
            "email": EMAIL,
            "method": "installment",
            "installment_months": 6,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["schedule"] == [331_667, 331_667, 331_667, 331_667, 331_666, 331_666]
    assert sum(body["schedule"]) == body["amount"] == 1_990_000


async def test_create_payment_unknown_promo_code_rejected(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Неизвестный промокод — 422, платёж не создаётся."""
    tariff_id = await _tariff_id(db, "basic")
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariff_id,
            "email": EMAIL,
            "method": "card",
            "promo_code": "UNKNOWN",
        },
    )
    assert response.status_code == 422
    assert (await _count_all(db)) == 0


async def test_create_payment_installment_without_months_rejected(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Рассрочка без срока рассрочки — 422, платёж не создаётся."""
    tariff_id = await _tariff_id(db, "standard")
    response = await client.post(
        "/payments",
        json={"tariff_id": tariff_id, "email": EMAIL, "method": "installment"},
    )
    assert response.status_code == 422
    assert (await _count_all(db)) == 0


async def test_create_payment_unknown_tariff_returns_404(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Неизвестный тариф — 404, платёж не создаётся."""
    response = await client.post(
        "/payments",
        json={"tariff_id": 99_999, "email": EMAIL, "method": "card"},
    )
    assert response.status_code == 404
    assert (await _count_all(db)) == 0


async def test_repeat_idempotency_key_does_not_duplicate(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Повторный запрос с тем же Idempotency-Key — 200 и тот же платёж, дубля нет."""
    tariff_id = await _tariff_id(db, "basic")
    key = "s5-repeat-key"
    payload = {"tariff_id": tariff_id, "email": EMAIL, "method": "card"}

    first = await client.post("/payments", json=payload, headers={"Idempotency-Key": key})
    assert first.status_code == 201

    second = await client.post("/payments", json=payload, headers={"Idempotency-Key": key})
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json() == first.json()

    assert await _count_by_key(db, key) == 1


async def test_create_payment_without_key_not_idempotent(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Без Idempotency-Key каждый запрос создаёт свой платёж."""
    tariff_id = await _tariff_id(db, "basic")
    payload = {"tariff_id": tariff_id, "email": EMAIL, "method": "card"}

    first = await client.post("/payments", json=payload)
    second = await client.post("/payments", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_get_existing_payment(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """``GET /payments/{id}`` по существующему платежу — 200 и его поля."""
    tariff_id = await _tariff_id(db, "basic")
    created = (
        await client.post(
            "/payments",
            json={"tariff_id": tariff_id, "email": EMAIL, "method": "card"},
        )
    ).json()

    response = await client.get(f"/payments/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["id"] == created["id"]
    assert body["amount"] == 990_000
    assert body["status"] == "pending"


async def test_get_missing_payment_returns_404(client: httpx.AsyncClient) -> None:
    """``GET /payments/{id}`` отсутствующего платежа — 404."""
    response = await client.get("/payments/999_999")
    assert response.status_code == 404
