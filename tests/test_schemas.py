import pytest
from pydantic import ValidationError

from app.schemas.payment import PaymentCreate


def _payload(**overrides):
    base = {
        "tariff_id": 1,
        "email": "user@example.com",
        "method": "card",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("method", ["card", "sbp"])
def test_valid_methods_without_installment(method: str) -> None:
    """``card``/``sbp`` без срока рассрочки — валидные."""
    PaymentCreate.model_validate(_payload(method=method))


@pytest.mark.parametrize("months", [3, 6, 12])
def test_valid_installment_with_months(months: int) -> None:
    """``installment`` с допустимым сроком (3/6/12) — валидный."""
    PaymentCreate.model_validate(_payload(method="installment", installment_months=months))


@pytest.mark.parametrize("months", [0, 1, 2, 4, 5, 8, 24, 120, -1])
def test_installment_months_out_of_range_rejected(months: int) -> None:
    """Срок вне набора {3, 6, 12} отклоняется (→ 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(method="installment", installment_months=months))


@pytest.mark.parametrize("method", ["cash", "bank", "INSTALLMENT", ""])
def test_invalid_method_rejected(method: str) -> None:
    """Недопустимый способ оплаты отклоняется (→ 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(method=method))


def test_installment_requires_months() -> None:
    """Рассрочка без срока рассрочки отклоняется (→ 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(method="installment"))


@pytest.mark.parametrize("method", ["card", "sbp"])
def test_non_installment_rejects_months(method: str) -> None:
    """Срок рассрочки для ``card``/``sbp`` отклоняется (→ 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(method=method, installment_months=3))


@pytest.mark.parametrize("email", ["not-an-email", "user@@", "@example.com", "user example.com"])
def test_invalid_email_rejected(email: str) -> None:
    """Некорректный email отклоняется (EmailStr, → 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(email=email))


@pytest.mark.parametrize("promo", ["KVITTO10", "kvitto10", "KViTtO10"])
def test_promo_code_case_insensitive_accepted(promo: str) -> None:
    """``KVITTO10`` принимается в любом регистре."""
    PaymentCreate.model_validate(_payload(promo_code=promo))


@pytest.mark.parametrize("promo", ["", "KVITTO", "KVITTO100", "PROMO", "KVITTO10 "])
def test_unknown_promo_code_rejected(promo: str) -> None:
    """Неизвестный промокод отклоняется (→ 422)."""
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(_payload(promo_code=promo))


def test_no_promo_code_is_optional() -> None:
    """Промокод необязателен: без него запрос валиден."""
    PaymentCreate.model_validate(_payload())
