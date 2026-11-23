import os
from decimal import Decimal, ROUND_HALF_UP

FREE_DELIVERY_LIMIT_LB = Decimal("20.00")
DELIVERY_CHARGE = Decimal("10.00")
CENTS = Decimal("0.01")

SERVICE_RADIUS_MILES = Decimal(os.environ.get("SERVICE_RADIUS_MILES", "25"))

TAX_RATE = Decimal(os.environ.get("TAX_RATE", "0.09375"))


# True when an address is within the delivery radius (exactly on the radius counts as inside).
def is_in_service_area(miles_from_store):
    return Decimal(str(miles_from_store)) <= SERVICE_RADIUS_MILES


# Sum of unit weight x quantity across a set of lines.
def calculate_total_weight(lines):
    total = Decimal("0.00")
    for line in lines:
        total += Decimal(line["unit_weight_lb"]) * line["quantity"]
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


# Free below 20 lb, $10.00 at 20 lb or more.
def calculate_delivery_fee(total_weight_lb):
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


# The full money breakdown for a cart or an order, in one place.
def price_lines(lines, tax_rate=None):
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


ORDER_STATUSES = [
    "placed",
    "awaiting_delivery",
    "assigned_to_trip",
    "out_for_delivery",
    "delivered",
]


# The one status an order may move to next, or None when delivered.
def next_status(current):
    index = ORDER_STATUSES.index(current)
    if index + 1 < len(ORDER_STATUSES):
        return ORDER_STATUSES[index + 1]
    return None


# True only for a single step forward
def is_forward_step(current, requested):
    return requested in ORDER_STATUSES and next_status(current) == requested


# None if a trip fits the vehicle, otherwise a sentence saying which limit it breaks.
def capacity_problem(order_count, total_weight_lb, max_orders, max_weight_lb):
    if order_count > max_orders:
        return f"Trip has {order_count} orders; the vehicle limit is {max_orders}"
    if Decimal(total_weight_lb) > Decimal(max_weight_lb):
        return (f"Trip weighs {Decimal(total_weight_lb)} lb; "
                f"the vehicle limit is {Decimal(max_weight_lb)} lb")
    return None


# Choose orders for one trip, oldest first.
def fill_trip(waiting_orders, max_orders, max_weight_lb):
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
