"""Rule arithmetic — NOT a feasibility test.

Be clear about what this file is and is not. It tests the delivery-charge
and weight logic, which is *business correctness*, not whether React,
Flask, MySQL or Tailwind are feasible. It is here for two smaller
reasons: it proves pytest itself installs and runs on both Windows and
Apple Silicon, and it de-risks the project's most consequential rule
before anyone builds on top of it.

The technology feasibility tests are in test_integration.py.

Cases come from the equivalence partitions in the High-Level Test Plan,
section IV.A.

Run:  pytest test_rules.py -v
"""

from decimal import Decimal

import pytest

from rules import calculate_delivery_fee, calculate_total_weight


# --- Feature 5.3, Calculate Delivery Cost -----------------------------

@pytest.mark.parametrize("weight,expected", [
    ("0.00",   "0.00"),    # Correct 1 — empty cart
    ("10.00",  "0.00"),    # Correct 1 — comfortably under
    ("19.99",  "0.00"),    # Correct 1 — EDGE, just under
    ("20.00",  "10.00"),   # Correct 2 — EDGE, exactly at the threshold
    ("20.01",  "10.00"),   # Correct 2 — just over
    ("200.00", "10.00"),   # Correct 2 — a full vehicle load
])
def test_delivery_fee_partitions(weight, expected):
    assert calculate_delivery_fee(Decimal(weight)) == Decimal(expected)


def test_exactly_twenty_pounds_is_charged():
    """The single most important assertion in the project. Free delivery
    applies only BELOW 20 lb, so 20.00 exactly is charged. Getting this
    backwards means every 20 lb order ships free."""
    assert calculate_delivery_fee(Decimal("20.00")) == Decimal("10.00")


# --- Feature 5.2, Calculate Total Weight ------------------------------

def test_empty_cart_weighs_nothing():
    assert calculate_total_weight([]) == Decimal("0.00")


def test_single_item_single_quantity():
    lines = [{"unit_weight_lb": Decimal("3.00"), "quantity": 1}]
    assert calculate_total_weight(lines) == Decimal("3.00")


def test_quantity_multiplies():
    lines = [{"unit_weight_lb": Decimal("3.00"), "quantity": 4}]
    assert calculate_total_weight(lines) == Decimal("12.00")


def test_several_items_sum():
    lines = [
        {"unit_weight_lb": Decimal("3.00"),  "quantity": 6},   # 18.00
        {"unit_weight_lb": Decimal("0.10"),  "quantity": 2},   #  0.20
    ]
    assert calculate_total_weight(lines) == Decimal("18.20")


def test_fractional_weights_do_not_drift():
    """The floating-point trap. In float arithmetic, 0.1 added ten times
    gives 0.9999999999999999, and a cart meant to sit at exactly 20.00 lb
    could land on the wrong side of the charge. Decimal must give 1.00."""
    lines = [{"unit_weight_lb": Decimal("0.10"), "quantity": 10}]
    assert calculate_total_weight(lines) == Decimal("1.00")

    # The same trap shown directly, for comparison:
    assert sum(0.1 for _ in range(10)) != 1.0        # float: fails
    assert sum(Decimal("0.10") for _ in range(10)) == Decimal("1.00")


def test_cart_can_land_exactly_on_the_threshold():
    """6 apple bags (18.00) + 20 lemons (2.00) = exactly 20.00 lb,
    which must be charged."""
    lines = [
        {"unit_weight_lb": Decimal("3.00"), "quantity": 6},
        {"unit_weight_lb": Decimal("0.10"), "quantity": 20},
    ]
    weight = calculate_total_weight(lines)
    assert weight == Decimal("20.00")
    assert calculate_delivery_fee(weight) == Decimal("10.00")
