"""Подпись вебхука: ``X-Signature`` — HMAC-SHA256 (hex) от исходного тела.

Проверка активна только при непустом ``WEBHOOK_SECRET``; в остальных
тестах набора секрет пуст (`.env`), поэтому проверка отключена.
"""

import hashlib
import hmac
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_asyncio import fixture
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.payment import Payment
from app.models.tariff import Tariff

EMAIL = "buyer@example.com"
SECRET = "test-webhook-secret"


@fixture(autouse=True)
async def clean_payments(db: AsyncSession) -> AsyncIterator[None]:
    """Удаляет платежи перед каждым тестом — тесты не зависят от порядка запуска."""
    await db.execute(delete(Payment))
    await db.commit()
    yield


@fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Включает проверку подписи на время теста (monkeypatch откатывает значение)."""
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", SECRET)


async def _tariff_id(db: AsyncSession) -> int:
    result = await db.execute(select(Tariff.id).where(Tariff.title == "basic"))
    return result.scalar_one()


async def _create_pending_payment(client: httpx.AsyncClient, db: AsyncSession) -> int:
    created = (
        await client.post(
            "/payments",
            json={
                "tariff_id": await _tariff_id(db),
                "email": EMAIL,
                "method": "card",
            },
        )
    ).json()
    assert created["status"] == "pending"
    return created["id"]


def _sign(payload: object, secret: str) -> tuple[bytes, str]:
    """Байты тела и его подпись: тело фиксируем явно, чтобы подпись сходилась побайтово."""
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, signature


async def _webhook_post(
    client: httpx.AsyncClient, payload: object, signature: str | None
) -> httpx.Response:
    """Отправляет вебхуку платёж с точным телом из ``payload`` и (опц.) подписью."""
    body, _ = _sign(payload, SECRET)
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Signature"] = signature
    return await client.post("/webhooks/bank", content=body, headers=headers)


async def _status_of(db: AsyncSession, payment_id: int) -> str:
    return (
        await db.execute(select(Payment.status).where(Payment.id == payment_id))
    ).scalar_one()


async def test_valid_signature_accepted(
    webhook_secret, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Корректная подпись: переход выполняется — 200, статус изменён."""
    payment_id = await _create_pending_payment(client, db)
    payload = {"payment_id": payment_id, "status": "succeeded"}
    _, signature = _sign(payload, SECRET)
    response = await _webhook_post(client, payload, signature)
    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert await _status_of(db, payment_id) == "succeeded"


async def test_invalid_signature_rejected(
    webhook_secret, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Неверная подпись — 401, платёж не тронут."""
    payment_id = await _create_pending_payment(client, db)
    payload = {"payment_id": payment_id, "status": "succeeded"}
    response = await _webhook_post(client, payload, "0" * 64)
    assert response.status_code == 401
    assert await _status_of(db, payment_id) == "pending"


async def test_missing_signature_rejected(
    webhook_secret, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Отсутствующая подпись при настроенном секрете — 401, платёж не тронут."""
    payment_id = await _create_pending_payment(client, db)
    payload = {"payment_id": payment_id, "status": "succeeded"}
    response = await _webhook_post(client, payload, None)
    assert response.status_code == 401
    assert await _status_of(db, payment_id) == "pending"


async def test_bad_signature_checked_before_payment_lookup(
    webhook_secret, client: httpx.AsyncClient
) -> None:
    """Проверка подписи первична: даже при неизвестном платеже неверная подпись — 401, а не 404."""
    response = await _webhook_post(client, {"payment_id": 999_999, "status": "succeeded"}, "0" * 64)
    assert response.status_code == 401


async def test_no_secret_means_check_disabled(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Секрет не настроен (пустой в `.env`): запрос без подписи принимается — 200."""
    payment_id = await _create_pending_payment(client, db)
    payload = {"payment_id": payment_id, "status": "succeeded"}
    response = await _webhook_post(client, payload, None)
    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert await _status_of(db, payment_id) == "succeeded"
