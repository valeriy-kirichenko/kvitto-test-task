# Промокод из ТЗ. Сравнение не зависит от регистра
PROMO_CODE = "KVITTO10"
# Размер скидки
PROMO_PERCENT = 10

# Маппинг статусов: из статуса можно перейти только в разрешённые
TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"succeeded", "failed"}),
    "succeeded": frozenset({"refunded"}),
    "failed": frozenset(),
    "refunded": frozenset(),
}


def promo_discount(price: int) -> int:
    """Скидка 10% от цены в копейках.

    Целочисленная арифметика, округление «вниз»: ``price * 10 // 100``.
    Заданные цены кратны 10, поэтому 10% — целое число копеек и
    округление потерь не даёт.
    """
    return price * PROMO_PERCENT // 100


def installments(total: int, months: int) -> list[int]:
    """Разбить сумму ``total`` (копейки) на ``months`` платежей.

    Лишние копейки от деления уходят **в первые платежи**: если
    ``divmod(total, months) == (base, remainder)``, то

    ``[base + 1] * remainder + [base] * (months - remainder)``,

    при этом ``sum(schedule) == total``.

    Предусловие ``months > 0`` обеспечивается валидацией на уровне
    схем (``Literal[3, 6, 12]``), здесь не дублируется.
    """
    base, remainder = divmod(total, months)
    return [base + 1] * remainder + [base] * (months - remainder)


def can_transition(current: str, target: str) -> bool:
    """Допустим ли переход ``current -> target``.

    Если ``current`` неизвестен, переход невозможен (``.get`` вернёт
    пустое множество) — так же, как при самопереходе или неизвестном
    ``target``.
    """
    return target in TRANSITIONS.get(current, frozenset())
