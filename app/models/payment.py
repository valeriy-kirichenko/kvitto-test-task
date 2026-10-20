from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Payment(BaseModel):
    """Платёж за тариф (копейки, без float).

    ``installment_months`` и ``schedule`` — только для рассрочки;
    для методов ``card``/``sbp`` оба поля ``null``.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    tariff_id: Mapped[int] = mapped_column(Integer, ForeignKey("tariffs.id"))
    amount: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    method: Mapped[str] = mapped_column(String(32))
    installment_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # График рассрочки: список целых чисел (копейки) или null.
    schedule: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    email: Mapped[str] = mapped_column(String(320))
    # Ключ идемпотентности необязателен; уникальность — на уровне БД.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
