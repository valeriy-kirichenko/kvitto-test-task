from pydantic import BaseModel, Field


class BankWebhookIn(BaseModel):
    """Запрос ``POST /webhooks/bank``.

    ``status`` — строка, а не Literal: запрещённый или неизвестный
    статус — это бизнес-правило (409 ``invalid_transition``), а не ошибка
    валидации формата (422).
    """

    payment_id: int = Field(
        description="Идентификатор платежа",
        examples=[1],
    )
    status: str = Field(
        description=(
            "Новый статус: pending, succeeded, failed или refunded; "
            "запрещённый переход и неизвестный статус — 409"
        ),
        examples=["succeeded"],
    )
