from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_asyncio import fixture
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.tariff import Tariff

EMAIL = "buyer@example.com"


@fixture(autouse=True)
async def clean_payments(db: AsyncSession) -> AsyncIterator[None]:
    """Удаляет платежи перед каждым тестом — тесты не зависят от порядка запуска."""
    await db.execute(delete(Payment))
    await db.commit()
    yield


async def _tariff_id(db: AsyncSession, title: str) -> int:
    result = await db.execute(select(Tariff.id).where(Tariff.title == title))
    return result.scalar_one()


async def _create_payment(client: httpx.AsyncClient, db: AsyncSession) -> int:
    """Создаёт новый платёж ``card``/``pending`` и возвращает его id."""
    created = (
        await client.post(
            "/payments",
            json={
                "tariff_id": await _tariff_id(db, "basic"),
                "email": EMAIL,
                "method": "card",
            },
        )
    ).json()
    assert created["status"] == "pending"
    return created["id"]


def _assert_ok(body: dict) -> None:
    """Точное тело успеха: ровно ``{"result": "ok"}``, без лишних полей."""
    assert body == {"result": "ok"}


def _assert_invalid(body: dict) -> None:
    """Точное тело ошибки: ровно ``{"error": "invalid_transition"}``."""
    assert body == {"error": "invalid_transition"}


async def test_webhook_unknown_payment_returns_404(client: httpx.AsyncClient) -> None:
    """Неизвестный ``payment_id`` — 404."""
    response = await client.post(
        "/webhooks/bank", json={"payment_id": 999_999, "status": "succeeded"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize("target", ["succeeded", "failed"])
async def test_webhook_pending_transitions_allowed(
    target: str, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """``pending → succeeded`` и ``pending → failed`` — 200, статус изменён в БД."""
    payment_id = await _create_payment(client, db)
    response = await client.post("/webhooks/bank", json={"payment_id": payment_id, "status": target})
    assert response.status_code == 200
    _assert_ok(response.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == target


async def test_webhook_succeeded_to_refunded_full_chain(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Полная разрешённая цепочка: pending → succeeded → refunded."""
    payment_id = await _create_payment(client, db)
    ok1 = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "succeeded"}
    )
    assert ok1.status_code == 200
    _assert_ok(ok1.json())

    ok2 = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "refunded"}
    )
    assert ok2.status_code == 200
    _assert_ok(ok2.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == "refunded"


async def test_webhook_forbidden_transition_returns_409_and_keeps_status(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """``pending → refunded`` запрещён: 409 с точным телом, статус не меняется."""
    payment_id = await _create_payment(client, db)
    response = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "refunded"}
    )
    assert response.status_code == 409
    _assert_invalid(response.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == "pending"


@pytest.mark.parametrize("current,target", [("pending", "pending"), ("succeeded", "succeeded")])
async def test_webhook_self_transition_forbidden(
    current: str, target: str, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Самопереход запрещён: 409, статус остаётся прежним."""
    payment_id = await _create_payment(client, db)
    if current == "succeeded":
        ok = await client.post(
            "/webhooks/bank", json={"payment_id": payment_id, "status": "succeeded"}
        )
        assert ok.status_code == 200

    response = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": target}
    )
    assert response.status_code == 409
    _assert_invalid(response.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == current


@pytest.mark.parametrize(
    ("seed", "target"),
    [
        ("failed", "pending"),
        ("failed", "succeeded"),
        ("failed", "refunded"),
        ("refunded", "pending"),
        ("refunded", "succeeded"),
        ("refunded", "failed"),
    ],
)
async def test_webhook_terminal_states_are_closed(
    seed: str, target: str, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Терминальные состояния ``failed``/``refunded``: любой следующий ход — 409."""
    payment_id = await _create_payment(client, db)
    if seed == "refunded":
        ok1 = await client.post(
            "/webhooks/bank", json={"payment_id": payment_id, "status": "succeeded"}
        )
        assert ok1.status_code == 200
        ok2 = await client.post(
            "/webhooks/bank", json={"payment_id": payment_id, "status": "refunded"}
        )
        assert ok2.status_code == 200
    else:
        ok = await client.post(
            "/webhooks/bank", json={"payment_id": payment_id, "status": seed}
        )
        assert ok.status_code == 200

    response = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": target}
    )
    assert response.status_code == 409
    _assert_invalid(response.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == seed


async def test_webhook_unknown_target_status_409(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Неизвестный целевой статус — 409 ``invalid_transition``, платёж не тронут."""
    payment_id = await _create_payment(client, db)
    response = await client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "chargeback"}
    )
    assert response.status_code == 409
    _assert_invalid(response.json())

    status = (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()
    assert status == "pending"
