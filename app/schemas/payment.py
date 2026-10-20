from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.domain import PROMO_CODE

PaymentMethod = Literal["card", "sbp", "installment"]
InstallmentMonths = Literal[3, 6, 12]


class PaymentCreate(BaseModel):
    """Запрос ``POST /payments``.

    Суммы (цена, скидка, итог, график) не передаются и не рассчитываются на
    клиенте: сервер берёт цену из тарифа, применяет промокод и строит график.
    Здесь описаны только поля входа и их валидация.
    """

    tariff_id: int = Field(
        description="Идентификатор тарифа",
        examples=[2],
    )
    email: EmailStr = Field(
        description="Email покупателя",
        examples=["user@example.com"],
    )
    method: PaymentMethod = Field(
        description="Способ оплаты: card, sbp или installment",
        examples=["card"],
    )
    installment_months: InstallmentMonths | None = Field(
        default=None,
        description="Срок рассрочки (3, 6 или 12); обязателен для installment, null для card/sbp",
        examples=[3],
    )
    promo_code: str | None = Field(
        default=None,
        description="Промокод скидки; регистр не важен; неизвестный код — 422",
        examples=["KVITTO10"],
    )

    @field_validator("promo_code")
    @classmethod
    def _validate_promo_code(cls, value: str | None) -> str | None:
        """Принимается только ``KVITTO10`` (регистр не важен), иначе — ошибка валидации (422)."""
        if value is not None and value.upper() != PROMO_CODE:
            raise ValueError("Неизвестный промокод")
        return value

    @model_validator(mode="after")
    def _validate_installment(self) -> "PaymentCreate":
        """Согласованность способа оплаты и срока рассрочки.

        Для ``installment`` срок обязателен; для ``card``/``sbp`` срок не
        передаётся. Несогласованные пары — ошибка валидации (422).
        """
        if self.method == "installment" and self.installment_months is None:
            raise ValueError("Для рассрочки обязателен installment_months (3, 6 или 12)")
        if self.method in ("card", "sbp") and self.installment_months is not None:
            raise ValueError("installment_months не используется для card/sbp")
        return self
