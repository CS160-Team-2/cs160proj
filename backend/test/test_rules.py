from decimal import Decimal

import pytest

from rules import (calculate_delivery_fee, calculate_tax, calculate_total_weight,
                   capacity_problem, fill_trip, is_forward_step, next_status, price_lines)


@pytest.mark.parametrize("weight,expected", [
    ("0.00",   "0.00"),
    ("10.00",  "0.00"),
    ("19.99",  "0.00"),
    ("20.00",  "10.00"),
    ("20.01",  "10.00"),
    ("200.00", "10.00"),
])
def test_delivery_fee_partitions(weight, expected):
    assert calculate_delivery_fee(Decimal(weight)) == Decimal(expected)


# The single most important assertion in the project.
def test_exactly_twenty_pounds_is_charged():
    assert calculate_delivery_fee(Decimal("20.00")) == Decimal("10.00")


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
        {"unit_weight_lb": Decimal("3.00"),  "quantity": 6},
        {"unit_weight_lb": Decimal("0.10"),  "quantity": 2},
    ]
    assert calculate_total_weight(lines) == Decimal("18.20")


# The floating-point trap.
def test_fractional_weights_do_not_drift():
    lines = [{"unit_weight_lb": Decimal("0.10"), "quantity": 10}]
    assert calculate_total_weight(lines) == Decimal("1.00")

    assert sum(Decimal("0.10") for _ in range(10)) == Decimal("1.00")


# 6 apple bags (18.00) + 20 lemons (2.00) = exactly 20.00 lb, which must be charged.
def test_cart_can_land_exactly_on_the_threshold():
    lines = [
        {"unit_weight_lb": Decimal("3.00"), "quantity": 6},
        {"unit_weight_lb": Decimal("0.10"), "quantity": 20},
    ]
    weight = calculate_total_weight(lines)
    assert weight == Decimal("20.00")
    assert calculate_delivery_fee(weight) == Decimal("10.00")


def test_tax_is_rounded_to_the_cent():
    assert calculate_tax(Decimal("10.00"), "0.09375") == Decimal("0.94")


def test_tax_applies_to_items_not_the_delivery_fee():
    lines = [{"price": Decimal("5.00"), "unit_weight_lb": Decimal("20.00"), "quantity": 1}]
    totals = price_lines(lines, tax_rate="0.10")

    assert totals["tax"] == Decimal("0.50")
    assert totals["delivery_fee"] == Decimal("10.00")
    assert totals["grand_total"] == Decimal("15.50")


def test_status_moves_forward_one_step():
    assert is_forward_step("placed", "awaiting_delivery")
    assert is_forward_step("out_for_delivery", "delivered")


@pytest.mark.parametrize("current,requested", [
    ("placed", "assigned_to_trip"),
    ("awaiting_delivery", "placed"),
    ("delivered", "delivered"),
    ("placed", "cancelled"),
])
def test_status_cannot_skip_or_go_back(current, requested):
    assert not is_forward_step(current, requested)


def test_delivered_is_the_last_status():
    assert next_status("delivered") is None


@pytest.mark.parametrize("orders,weight,fits", [
    (9, "100.00", True),
    (10, "100.00", True),
    (11, "100.00", False),
    (5, "199.99", True),
    (5, "200.00", True),
    (5, "200.01", False),
    (10, "200.00", True),
])
def test_capacity_limits(orders, weight, fits):
    problem = capacity_problem(orders, Decimal(weight), 10, Decimal("200.00"))
    assert (problem is None) == fits


def _orders(*weights):
    return [{"order_id": i + 1, "total_weight_lb": Decimal(w)} for i, w in enumerate(weights)]


def test_fill_trip_stops_at_ten_orders():
    chosen, too_heavy = fill_trip(_orders(*["1.00"] * 11), 10, Decimal("200.00"))
    assert [o["order_id"] for o in chosen] == list(range(1, 11))
    assert too_heavy == []


def test_fill_trip_stops_at_the_weight_limit_before_the_order_limit():
    chosen, _ = fill_trip(_orders("150.00", "60.00", "50.00"), 10, Decimal("200.00"))
    assert [o["order_id"] for o in chosen] == [1, 3]


def test_fill_trip_reports_an_order_heavier_than_the_vehicle():
    chosen, too_heavy = fill_trip(_orders("201.00", "5.00"), 10, Decimal("200.00"))
    assert [o["order_id"] for o in too_heavy] == [1]
    assert [o["order_id"] for o in chosen] == [2]


def test_fill_trip_takes_the_oldest_orders_first():
    chosen, _ = fill_trip(_orders(*["20.00"] * 12), 10, Decimal("200.00"))
    assert [o["order_id"] for o in chosen] == list(range(1, 11))
