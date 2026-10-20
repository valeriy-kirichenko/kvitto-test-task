"""``GET /payments``: список платежей с фильтрами по email и статусу."""

from collections.abc import AsyncIterator

import httpx
from pytest_asyncio import fixture
from sqlalchemy import delete, select

from app.models.payment import Payment
from app.models.tariff import Tariff

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"
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
async def clean_payments(db) -> AsyncIterator[None]:
    """Удаляет платежи перед каждым тестом — тесты не зависят от порядка запуска."""
    await db.execute(delete(Payment))
    await db.commit()
    yield


async def _tariff_id(db) -> int:
    result = await db.execute(select(Tariff.id).where(Tariff.title == "basic"))
    return result.scalar_one()


async def _create(client: httpx.AsyncClient, db, email: str) -> int:
    created = (
        await client.post(
            "/payments",
            json={"tariff_id": await _tariff_id(db), "email": email, "method": "card"},
        )
    ).json()
    assert created["status"] == "pending"
    return created["id"]


async def _transition(client: httpx.AsyncClient, payment_id: int, status: str) -> None:
    response = await client.post("/webhooks/bank", json={"payment_id": payment_id, "status": status})
    assert response.status_code == 200
    assert response.json() == {"result": "ok"}


async def test_list_payments_returns_all(client: httpx.AsyncClient, db) -> None:
    """Без фильтров — все платежи, в порядке создания, с полным набором полей."""
    first = await _create(client, db, EMAIL_A)
    second = await _create(client, db, EMAIL_B)

    response = await client.get("/payments")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [first, second]
    for item in body:
        assert set(item) == RESPONSE_FIELDS
    assert body[0]["email"] == EMAIL_A
    assert body[1]["email"] == EMAIL_B


async def test_list_payments_filter_by_email(client: httpx.AsyncClient, db) -> None:
    """Фильтр ``email`` — только платежи этого покупателя."""
    target = await _create(client, db, EMAIL_A)
    await _create(client, db, EMAIL_B)

    response = await client.get("/payments", params={"email": EMAIL_A})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [target]
    assert body[0]["email"] == EMAIL_A


async def test_list_payments_filter_by_status(client: httpx.AsyncClient, db) -> None:
    """Фильтр ``status`` — только платежи с заданным статусом."""
    pending_id = await _create(client, db, EMAIL_A)
    succeeded_id = await _create(client, db, EMAIL_B)
    await _transition(client, succeeded_id, "succeeded")

    response = await client.get("/payments", params={"status": "pending"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [pending_id]

    response = await client.get("/payments", params={"status": "succeeded"})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [succeeded_id]
    assert body[0]["status"] == "succeeded"


async def test_list_payments_combined_filters(client: httpx.AsyncClient, db) -> None:
    """Совмещение фильтров: только платёж, подходящий по email и по статусу."""
    target = await _create(client, db, EMAIL_A)
    await _create(client, db, EMAIL_B)
    await _transition(client, target, "succeeded")

    # email сходится в обоих, статус — только у первого:
    response = await client.get(
        "/payments", params={"email": EMAIL_A, "status": "succeeded"}
    )
    assert [item["id"] for item in response.json()] == [target]

    # статус не сходится ни с одним:
    response = await client.get(
        "/payments", params={"email": EMAIL_A, "status": "pending"}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_payments_filter_without_match(client: httpx.AsyncClient, db) -> None:
    """Фильтр без совпадений — 200 и пустой список."""
    await _create(client, db, EMAIL_A)

    response = await client.get("/payments", params={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert response.json() == []
