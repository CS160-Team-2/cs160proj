"""The two OFS rules, as pure functions with no I/O.

These are features 5.2 and 5.3 from the Low-Level Design Document.
They are here in the spike so the arithmetic can be proven correct
before anything is built on top of it.
"""

from decimal import Decimal, ROUND_HALF_UP

FREE_DELIVERY_LIMIT_LB = Decimal("20.00")
DELIVERY_CHARGE = Decimal("10.00")
CENTS = Decimal("0.01")


def calculate_total_weight(lines):
    """Feature 5.2 — sum unit weight x quantity across a set of lines.

    `lines` is a list of dicts with 'unit_weight_lb' (Decimal) and
    'quantity' (int).
    """
    total = Decimal("0.00")
    for line in lines:
        total += Decimal(line["unit_weight_lb"]) * line["quantity"]
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


def calculate_delivery_fee(total_weight_lb):
    """Feature 5.3 — free below 20 lb, $10.00 at 20 lb or more.

    Note `<` not `<=`: an order of exactly 20.00 lb IS charged, because
    free delivery applies only *below* the threshold.
    """
    if Decimal(total_weight_lb) < FREE_DELIVERY_LIMIT_LB:
        return Decimal("0.00")
    return DELIVERY_CHARGE


def calculate_subtotal(lines):
    total = Decimal("0.00")
    for line in lines:
        total += Decimal(line["price"]) * line["quantity"]
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)
