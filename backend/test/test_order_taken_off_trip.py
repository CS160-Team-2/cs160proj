import pytest

from conftest import ready_order, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


# Makes a waiting order and a planned trip holding it; returns (order_id, order_number, trip).
def planned_trip(customer, manager, weight="4.00"):
    order_id = ready_order(customer, manager, weight=weight)
    number = [o for o in manager.get("/api/admin/delivery/queue").get_json()["orders"] if o["order_id"] == order_id][0]["order_number"]
    trip = manager.post("/api/admin/delivery/trips", json={"order_ids": [order_id]}).get_json()["trip"]
    return order_id, number, trip


# The customer's own progress steps as (status, done) pairs.
def steps(customer, number):
    return [(s["status"], s["done"]) for s in customer.get(f"/api/orders/{number}/tracking").get_json()["steps"]]


def test_customer_steps_follow_the_order_back_when_it_is_taken_off_its_trip(customer, manager):
    order_id, number, trip = planned_trip(customer, manager)
    assert steps(customer, number)[2] == ("assigned_to_trip", True)

    manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}/orders/{order_id}")

    tracking = customer.get(f"/api/orders/{number}/tracking").get_json()
    assert tracking["status"] == "awaiting_delivery"
    assert steps(customer, number) == [("placed", True), ("awaiting_delivery", True), ("assigned_to_trip", False),
                                       ("out_for_delivery", False), ("delivered", False)]
    assert "took your order off" in tracking["notice"]
    assert tracking["estimated_arrival"] is None and tracking["map"]["preview"] is True
    assert customer.get("/api/orders").get_json()["orders"][0]["status"] == "awaiting_delivery"


def test_the_notice_goes_away_when_the_order_is_put_on_a_new_trip(customer, manager):
    order_id, number, trip = planned_trip(customer, manager)
    manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}/orders/{order_id}")
    manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/orders", json={"order_id": order_id})

    tracking = customer.get(f"/api/orders/{number}/tracking").get_json()

    assert tracking["status"] == "assigned_to_trip" and tracking["notice"] is None
    assert steps(customer, number)[2] == ("assigned_to_trip", True)


def test_an_order_that_was_never_on_a_trip_has_no_notice(customer, manager):
    ready_order(customer, manager)
    number = manager.get("/api/admin/delivery/queue").get_json()["orders"][0]["order_number"]

    assert customer.get(f"/api/orders/{number}/tracking").get_json()["notice"] is None


def test_the_history_records_the_move_back(customer, manager):
    order_id, number, trip = planned_trip(customer, manager)

    manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}/orders/{order_id}")

    history = customer.get(f"/api/orders/{number}/tracking").get_json()["history"]
    assert [h["status"] for h in history] == ["placed", "awaiting_delivery", "assigned_to_trip", "awaiting_delivery"]


def test_the_employee_sees_the_order_waiting_again_and_no_empty_trip(customer, manager, employee):
    order_id, number, trip = planned_trip(customer, manager)

    manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}/orders/{order_id}")

    assert employee.get("/api/staff/delivery/trips").get_json()["trips"] == []
    assert [w["order_number"] for w in employee.get("/api/staff/delivery/board").get_json()["waiting"]] == [number]
    assert [t["trip_id"] for t in manager.get("/api/admin/delivery/trips").get_json()["trips"]] == [trip["trip_id"]]


def test_a_trip_cannot_be_cancelled_there_is_no_such_route(customer, manager):
    order_id, number, trip = planned_trip(customer, manager)

    assert manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}").status_code == 405
    assert customer.get(f"/api/orders/{number}/tracking").get_json()["status"] == "assigned_to_trip"


def test_an_order_can_be_added_to_a_trip_that_was_emptied(customer, manager):
    order_id, number, trip = planned_trip(customer, manager)
    manager.delete(f"/api/admin/delivery/trips/{trip['trip_id']}/orders/{order_id}")
    other = ready_order(customer, manager, weight="3.00")

    response = manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/orders", json={"order_id": other})

    assert response.status_code == 200
    assert response.get_json()["trip"]["order_count"] == 1
