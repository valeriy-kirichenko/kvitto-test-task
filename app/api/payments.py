from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domain import installments, promo_discount
from app.models.payment import Payment
from app.models.tariff import Tariff
from app.schemas.payment import PaymentCreate, PaymentOut

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


@router.post(
    "",
    response_model=PaymentOut,
    status_code=201,
    summary="Создать платёж",
    description=(
        "Создаёт платёж со статусом `pending`. Цена берётся из тарифа БД, "
        "скидка рассчитывается по промокоду, график — через `domain.installments`. "
        "Повторный запрос с тем же заголовком `Idempotency-Key` возвращает "
        "ранее созданный платёж с кодом 200, дубликат не создаётся."
    ),
    responses={
        201: {
            "description": "Платёж создан",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "status": "pending",
                        "tariff_id": 2,
                        "amount": 1791000,
                        "discount": 199000,
                        "method": "card",
                        "installment_months": None,
                        "schedule": None,
                        "email": "user@example.com",
                        "created_at": "2026-10-20T12:00:00Z",
                    }
                }
            },
        },
        200: {"description": "Платёж уже создан с этим Idempotency-Key"},
        404: {"description": "Тариф не найден"},
        422: {"description": "Ошибка валидации входных данных"},
    },
)
async def create_payment(
    body: PaymentCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Payment:
    """``POST /payments``: создать платёж или вернуть уже созданный (идемпотентно)."""
    # Идемпотентность проверяется до валидации тарифа: повторный запрос
    # возвращает первый платёж даже при ином теле запроса.
    if idempotency_key is not None:
        existing = (
            await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing is not None:
            response.status_code = 200
            return existing

    tariff = (
        await db.execute(select(Tariff).where(Tariff.id == body.tariff_id))
    ).scalar_one_or_none()
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    discount = promo_discount(tariff.price) if body.promo_code is not None else 0
    amount = tariff.price - discount
    if body.method == "installment":
        schedule = installments(amount, body.installment_months)
        months = body.installment_months
    else:
        schedule = None
        months = None

    payment = Payment(
        status="pending",
        tariff_id=body.tariff_id,
        amount=amount,
        discount=discount,
        method=body.method,
        installment_months=months,
        schedule=schedule,
        email=body.email,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    try:
        await db.commit()
    except IntegrityError:
        # Конкурентный запрос уже занял уникальный ключ идемпотентности:
        # откатываем вставку и перечитываем созданный раньше платёж.
        await db.rollback()
        existing = (
            await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        ).scalar_one()
        response.status_code = 200
        return existing

    await db.refresh(payment)
    return payment


@router.get(
    "",
    response_model=list[PaymentOut],
    summary="Список платежей",
    description=(
        "Список платежей в порядке создания. Необязательные фильтры: "
        "`email` (email покупателя) и `status` (статус платежа). "
        "Без совпадений возвращается пустой список."
    ),
    responses={
        200: {
            "description": "Список платежей",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "status": "pending",
                            "tariff_id": 2,
                            "amount": 1791000,
                            "discount": 199000,
                            "method": "card",
                            "installment_months": None,
                            "schedule": None,
                            "email": "user@example.com",
                            "created_at": "2026-10-20T12:00:00Z",
                        }
                    ]
                }
            },
        }
    },
)
async def list_payments(
    db: AsyncSession = Depends(get_db),
    email: str | None = Query(default=None, description="Фильтр по email покупателя"),
    status: str | None = Query(default=None, description="Фильтр по статусу платежа"),
) -> list[Payment]:
    """``GET /payments``: список платежей с необязательными фильтрами."""
    stmt = select(Payment)
    if email is not None:
        stmt = stmt.where(Payment.email == email)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    result = await db.execute(stmt.order_by(Payment.id))
    return list(result.scalars().all())


@router.get(
    "/{payment_id}",
    response_model=PaymentOut,
    summary="Получить платёж",
    description="Возвращает платёж по идентификатору; 404, если платежа нет.",
    responses={
        200: {"description": "Платёж найден"},
        404: {"description": "Платёж не найден"},
    },
)
async def get_payment(payment_id: int, db: AsyncSession = Depends(get_db)) -> Payment:
    """``GET /payments/{id}``: платёж по идентификатору или 404."""
    payment = (
        await db.execute(select(Payment).where(Payment.id == payment_id))
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    return payment
