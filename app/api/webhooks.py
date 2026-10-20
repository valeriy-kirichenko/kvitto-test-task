from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domain import can_transition
from app.models.payment import Payment
from app.schemas.webhook import BankWebhookIn

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


@router.post(
    "/bank",
    summary="Уведомление банка о смене статуса",
    description=(
        "Банк сообщает о смене статуса платежа. Разрешённые переходы: "
        "`pending → succeeded`, `pending → failed`, `succeeded → refunded`; "
        "все остальные (включая самопереходы) — 409 со статусом, не изменённым."
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
async def bank_webhook(body: BankWebhookIn, db: AsyncSession = Depends(get_db)):
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
