import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.domain import can_transition
from app.models.payment import Payment
from app.schemas.webhook import BankWebhookIn

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


async def verify_signature(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
) -> None:
    """Проверка подписи тела вебхука, если настроен секрет.

    ``X-Signature`` — hex-значение HMAC-SHA256 от **исходного** тела
    запроса, вычисленное с секретом ``WEBHOOK_SECRET``. Сравнение идёт
    через ``hmac.compare_digest`` (защита от атак по времени).

    ``WEBHOOK_SECRET`` пустой или не задан — проверка отключена
    (dev-режим). При настроенном секрете отсутствующая или
    неверная подпись — ``401``.
    """
    secret = settings.WEBHOOK_SECRET
    if not secret:
        return

    raw_body = await request.body()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if (
        x_signature is None
        or not hmac.compare_digest(
            x_signature.encode("utf-8"), expected.encode("utf-8")
        )
    ):
        raise HTTPException(status_code=401, detail="Неверная или отсутствующая подпись")


@router.post(
    "/bank",
    summary="Уведомление банка о смене статуса",
    description=(
        "Банк сообщает о смене статуса платежа. Разрешённые переходы: "
        "`pending → succeeded`, `pending → failed`, `succeeded → refunded`; "
        "все остальные (включая самопереходы) — 409 со статусом, не изменённым.\n"
        "Если настроен `WEBHOOK_SECRET`, запрос обязан содержать заголовок "
        "`X-Signature` — HMAC-SHA256 (hex) от исходного тела запроса; "
        "иначе — `401`."
    ),
    responses={
        200: {
            "description": "Переход выполнен",
            "content": {
                "application/json": {
                    "example": {"result": "ok"}
                }
            },
        },
        401: {
            "description": (
                "Неверная или отсутствующая подпись X-Signature "
                "(когда настроен WEBHOOK_SECRET)"
            )
        },
        404: {"description": "Платёж не найден"},
        409: {
            "description": "Переход запрещён, статус не изменён",
            "content": {
                "application/json": {
                    "example": {"error": "invalid_transition"}
                }
            },
        },
        422: {"description": "Ошибка валидации входных данных"},
    },
)
async def bank_webhook(
    body: BankWebhookIn,
    # Проверка подписи выполняется до доступа к БД: при неверной или
    # отсутствующей подписи (когда секрет настроен) — 401.
    signature: None = Depends(verify_signature),
    db: AsyncSession = Depends(get_db),
):
    """``POST /webhooks/bank``: сменить статус платежа или отклонить переход.

    Запрос к платежу идёт с ``FOR UPDATE``: строка блокируется до
    commit/rollback транзакции, поэтому два конкурентных уведомления не
    прочитывают одновременно одно и то же «старое» значение статуса.
    """
    payment = (
        await db.execute(
            select(Payment)
            .where(Payment.id == body.payment_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    if not can_transition(payment.status, body.status):
        # Запрещённый переход: статус не трогаем, коммит не выполняем —
        # сессия закрывается, ожидающая транзакция откатывается.
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})

    payment.status = body.status
    await db.commit()
    return {"result": "ok"}
