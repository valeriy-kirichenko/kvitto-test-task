"""Юнит-тесты чистого домена: деньги, график рассрочки, статусы.

Без БД и ORM — проверяются результаты чистых функций.
"""

import pytest

from app.domain import (
    TRANSITIONS,
    can_transition,
    installments,
    promo_discount,
)

# Цены тарифов из ТЗ, в копейках.
BASIC = 990_000
STANDARD = 1_990_000
PREMIUM = 2_990_000


# --- деньги: промо-скидка ---------------------------------------------------


@pytest.mark.parametrize(
    ("price", "discount"),
    [
        (BASIC, 99_000),
        (STANDARD, 199_000),  # standard: 1_990_000 -> 199_000
        (PREMIUM, 299_000),
    ],
)
def test_promo_discount_matches_spec(price: int, discount: int) -> None:
    assert promo_discount(price) == discount


def test_promo_discount_is_integral() -> None:
    assert isinstance(promo_discount(STANDARD), int)
    assert isinstance(promo_discount(BASIC), int)


@pytest.mark.parametrize("price", [BASIC, STANDARD, PREMIUM])
def test_promo_invariants(price: int) -> None:
    """Инварианты: amount + discount == price, amount > 0, 0 <= discount <= price."""
    discount = promo_discount(price)
    amount = price - discount
    assert amount + discount == price
    assert amount > 0
    assert 0 <= discount <= price


# --- график рассрочки -------------------------------------------------------


@pytest.mark.parametrize("months", [3, 6, 12])
def test_installments_sum_and_length(months: int) -> None:
    schedule = installments(STANDARD, months)
    assert len(schedule) == months
    assert sum(schedule) == STANDARD


def test_installments_standard_3_months() -> None:
    """Пример из ТЗ: standard без промо, 3 месяца."""
    assert installments(STANDARD, 3) == [663_334, 663_333, 663_333]


def test_installments_standard_6_months() -> None:
    assert installments(STANDARD, 6) == [331_667, 331_667, 331_667, 331_667, 331_666, 331_666]


def test_installments_standard_12_months() -> None:
    # [165_834]*4 + [165_833]*8 — сумма 1_990_000.
    assert installments(STANDARD, 12) == [165_834] * 4 + [165_833] * 8


def test_installments_promo_amount_splits_evenly() -> None:
    """Standard с KVITTO10: 1_791_000 делится на 3 месяца без остатка."""
    amount = STANDARD - promo_discount(STANDARD)
    assert amount == 1_791_000
    assert installments(amount, 3) == [597_000, 597_000, 597_000]


def test_installments_remainder_goes_to_first_payments() -> None:
    """Лишние копейки — в первых платежах; график неотрицательно нерастущий, целочисленный."""
    schedule = installments(STANDARD, 6)
    assert all(isinstance(payment, int) for payment in schedule)
    assert all(a >= b for a, b in zip(schedule, schedule[1:]))


# --- маппинг статусов --------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "succeeded"),
        ("pending", "failed"),
        ("succeeded", "refunded"),
    ],
)
def test_can_transition_allowed(current: str, target: str) -> None:
    assert can_transition(current, target) is True


@pytest.mark.parametrize(
    ("current", "target"),
    [
        # самопереходы запрещены
        ("pending", "pending"),
        ("succeeded", "succeeded"),
        # прямые запреты из ТЗ
        ("pending", "refunded"),
        ("succeeded", "failed"),
        ("succeeded", "pending"),
        # терминальные состояния
        ("failed", "pending"),
        ("failed", "succeeded"),
        ("failed", "failed"),
        ("refunded", "pending"),
        ("refunded", "succeeded"),
        ("refunded", "failed"),
        ("refunded", "refunded"),
        # неизвестные статусы
        ("unknown", "succeeded"),
        ("pending", "unknown_status"),
    ],
)
def test_can_transition_forbidden(current: str, target: str) -> None:
    assert can_transition(current, target) is False


def test_terminal_states_are_closed() -> None:
    assert TRANSITIONS["failed"] == frozenset()
    assert TRANSITIONS["refunded"] == frozenset()


def test_status_universe_is_consistent() -> None:
    """Всего 4 статуса, и все цели переходов — из этого же множества."""
    known = {"pending", "succeeded", "failed", "refunded"}
    assert set(TRANSITIONS) == known
    for targets in TRANSITIONS.values():
        assert targets <= known
