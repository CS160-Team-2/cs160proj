"""OFS business rules, as pure functions with no database or network.

Everything here is a rule from the design document that more than one
part of the system must apply identically: the cart, checkout and the
delivery planner all call the same functions, so their numbers can never
disagree. Keeping them free of I/O is what lets test_rules.py check them
exhaustively without a database.
"""

import os
from decimal import Decimal, ROUND_HALF_UP

FREE_DELIVERY_LIMIT_LB = Decimal("20.00")
DELIVERY_CHARGE = Decimal("10.00")
CENTS = Decimal("0.01")

# Sales tax on the item subtotal (not on the delivery fee). Defaults to
# the San Jose rate; set TAX_RATE in .env to change it.
TAX_RATE = Decimal(os.environ.get("TAX_RATE", "0.09375"))


def calculate_total_weight(lines):
    """Sum of unit weight x quantity across a set of lines.

    `lines` is a list of dicts with 'unit_weight_lb' (Decimal) and
    'quantity' (int).
    """
    total = Decimal("0.00")
    for line in lines:
        total += Decimal(line["unit_weight_lb"]) * line["quantity"]
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


def calculate_delivery_fee(total_weight_lb):
    """Free below 20 lb, $10.00 at 20 lb or more.

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


def calculate_tax(subtotal, rate=None):
    rate = TAX_RATE if rate is None else Decimal(rate)
    return (Decimal(subtotal) * rate).quantize(CENTS, rounding=ROUND_HALF_UP)


def price_lines(lines, tax_rate=None):
    """The full money breakdown for a cart or an order, in one place."""
    subtotal = calculate_subtotal(lines)
    weight = calculate_total_weight(lines)
    fee = calculate_delivery_fee(weight)
    tax = calculate_tax(subtotal, tax_rate)
    return {
        "subtotal": subtotal,
        "total_weight_lb": weight,
        "delivery_fee": fee,
        "tax": tax,
        "grand_total": subtotal + tax + fee,
    }


# =====================================================================
# Order status
# =====================================================================

ORDER_STATUSES = [
    "placed",
    "awaiting_delivery",
    "assigned_to_trip",
    "out_for_delivery",
    "delivered",
]


def next_status(current):
    """The one status an order may move to next, or None when delivered."""
    index = ORDER_STATUSES.index(current)
    if index + 1 < len(ORDER_STATUSES):
        return ORDER_STATUSES[index + 1]
    return None


def is_forward_step(current, requested):
    """True only for a single step forward: no going back, no skipping."""
    return requested in ORDER_STATUSES and next_status(current) == requested


# =====================================================================
# Vehicle capacity and trip building
# =====================================================================

def capacity_problem(order_count, total_weight_lb, max_orders, max_weight_lb):
    """None if a trip fits the vehicle, otherwise a sentence saying which
    limit it breaks. Both limits apply at the same time."""
    if order_count > max_orders:
        return f"Trip has {order_count} orders; the vehicle limit is {max_orders}"
    if Decimal(total_weight_lb) > Decimal(max_weight_lb):
        return (f"Trip weighs {Decimal(total_weight_lb)} lb; "
                f"the vehicle limit is {Decimal(max_weight_lb)} lb")
    return None


def fill_trip(waiting_orders, max_orders, max_weight_lb):
    """Choose orders for one trip, oldest first.

    `waiting_orders` is oldest-first, each a dict with 'order_id' and
    'total_weight_lb'. Returns (chosen, too_heavy):

      chosen     orders that fit together within both limits
      too_heavy  orders heavier than the vehicle can ever carry alone

    Anything in neither list stays in the queue for the next trip. An
    order that does not fit is skipped rather than ending the search, so
    a lighter order behind it can still use the remaining space.
    """
    max_weight_lb = Decimal(max_weight_lb)
    chosen, too_heavy = [], []
    weight = Decimal("0.00")

    for order in waiting_orders:
        order_weight = Decimal(order["total_weight_lb"])
        if order_weight > max_weight_lb:
            too_heavy.append(order)
            continue
        if len(chosen) + 1 > max_orders:
            continue
        if weight + order_weight > max_weight_lb:
            continue
        chosen.append(order)
        weight += order_weight

    return chosen, too_heavy
