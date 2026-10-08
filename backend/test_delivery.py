"""Delivery trips, routing, dispatch and vehicle callbacks (API tables IX
and X; backlog B-10, B-11, B-12; test plan T-07, T-09, T-10)."""

import pytest

import db as database
from conftest import (OTHER_VEHICLE_TOKEN, VEHICLE_TOKEN, error_code, ready_order,
                      requires_mysql)
from services import mapping, vehicle

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def status_of(order_id):
    return database.query_one("SELECT status FROM orders WHERE order_id = %s",
                              (order_id,))["status"]


# --- The whole manager workflow, start to finish ----------------------

def test_order_goes_from_placed_to_delivered(client, customer, manager):
    order_id = ready_order(customer, manager, weight="4.00")
    assert [o["order_id"] for o in manager.get("/api/admin/delivery/queue").get_json()["orders"]] == [order_id]

    created = manager.post("/api/admin/delivery/trips", json={})
    assert created.status_code == 201
    trip = created.get_json()["trip"]
    assert trip["route_planned"] is True and trip["capacity_problem"] is None
    assert trip["stops"][0]["est_arrival"] is not None
    assert status_of(order_id) == "assigned_to_trip"

    number = trip["stops"][0]["order_number"]
    assert customer.get(f"/api/orders/{number}/tracking").get_json()["estimated_arrival"]

    dispatched = manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    assert dispatched.get_json()["trip"]["status"] == "out_for_delivery"
    assert status_of(order_id) == "out_for_delivery"
    assert vehicle.link().sent[0]["stops"][0]["order_id"] == order_id

    done = client.post(f"/api/fleet/trips/{trip['trip_id']}/stops/{order_id}/completed",
                       headers=bearer(VEHICLE_TOKEN))
    assert done.get_json()["trip_status"] == "completed"

    tracking = customer.get(f"/api/orders/{number}/tracking").get_json()
    assert tracking["status"] == "delivered" and tracking["delivered_at"]
    assert all(step["done"] for step in tracking["steps"])
    vehicles = manager.get("/api/admin/delivery/vehicles").get_json()["vehicles"]
    assert vehicles[0]["status"] == "available"


# --- Capacity: 10 orders and 200 lb (T-07) ----------------------------

def test_an_eleventh_order_waits_for_the_next_trip(customer, manager):
    order_ids = [ready_order(customer, manager) for _ in range(11)]
    response = manager.post("/api/admin/delivery/trips", json={})

    assert response.get_json()["trip"]["order_count"] == 10
    assert len(response.get_json()["left_waiting"]) == 1
    assert status_of(order_ids[-1]) == "awaiting_delivery"


def test_weight_limit_is_hit_before_the_order_limit(customer, manager):
    heavy = [ready_order(customer, manager, weight="90.00") for _ in range(3)]
    trip = manager.post("/api/admin/delivery/trips", json={}).get_json()["trip"]

    assert trip["order_count"] == 2 and trip["total_weight_lb"] == "180.00"
    assert status_of(heavy[2]) == "awaiting_delivery"


def test_an_order_heavier_than_the_vehicle_is_reported(customer, manager):
    too_heavy = ready_order(customer, manager, weight="201.00")
    response = manager.post("/api/admin/delivery/trips", json={})

    assert error_code(response) == "NOTHING_TO_SCHEDULE"
    exceptions = manager.get("/api/admin/delivery/exceptions").get_json()["orders"]
    assert exceptions[0]["order_id"] == too_heavy
    assert "Too heavy" in exceptions[0]["reason"]


def test_choosing_orders_that_break_a_limit_is_refused(customer, manager):
    ids = [ready_order(customer, manager, weight="101.00") for _ in range(2)]
    response = manager.post("/api/admin/delivery/trips", json={"order_ids": ids})
    assert error_code(response) == "CAPACITY_EXCEEDED"
    assert all(status_of(i) == "awaiting_delivery" for i in ids)


def test_adding_an_order_rechecks_the_limits(customer, manager):
    first = ready_order(customer, manager, weight="150.00")
    second = ready_order(customer, manager, weight="60.00")
    trip_id = manager.post("/api/admin/delivery/trips",
                           json={"order_ids": [first]}).get_json()["trip"]["trip_id"]

    response = manager.post(f"/api/admin/delivery/trips/{trip_id}/orders",
                            json={"order_id": second})
    assert error_code(response) == "CAPACITY_EXCEEDED"


# --- Changing a trip before it leaves ---------------------------------

def test_add_and_remove_orders_replans_the_route(customer, manager):
    first = ready_order(customer, manager)
    second = ready_order(customer, manager)
    trip_id = manager.post("/api/admin/delivery/trips",
                           json={"order_ids": [first]}).get_json()["trip"]["trip_id"]

    added = manager.post(f"/api/admin/delivery/trips/{trip_id}/orders",
                         json={"order_id": second}).get_json()["trip"]
    assert added["order_count"] == 2
    assert sorted(s["stop_sequence"] for s in added["stops"]) == [1, 2]

    removed = manager.delete(f"/api/admin/delivery/trips/{trip_id}/orders/{first}")
    assert removed.get_json()["trip"]["order_count"] == 1
    assert status_of(first) == "awaiting_delivery"


def test_a_dispatched_trip_cannot_change(customer, manager):
    order_id = ready_order(customer, manager)
    trip_id = manager.post("/api/admin/delivery/trips", json={}).get_json()["trip"]["trip_id"]
    manager.post(f"/api/admin/delivery/trips/{trip_id}/dispatch")

    assert error_code(manager.post(f"/api/admin/delivery/trips/{trip_id}/route")) == "TRIP_ALREADY_DISPATCHED"
    assert error_code(manager.delete(
        f"/api/admin/delivery/trips/{trip_id}/orders/{order_id}")) == "TRIP_ALREADY_DISPATCHED"


def test_a_trip_without_a_route_cannot_be_dispatched(customer, manager):
    class BrokenMap(mapping.FakeMapProvider):
        def route(self, origin, stops):
            raise mapping.MappingError("Mapping service down")
    mapping.use_provider(BrokenMap())

    ready_order(customer, manager)
    created = manager.post("/api/admin/delivery/trips", json={}).get_json()
    assert created["route_error"] == "Mapping service down"

    response = manager.post(f"/api/admin/delivery/trips/{created['trip']['trip_id']}/dispatch")
    assert error_code(response) == "NO_ROUTE"


def test_a_vehicle_with_a_trip_is_not_given_another(customer, manager):
    ready_order(customer, manager)
    ready_order(customer, manager)
    manager.post("/api/admin/delivery/trips", json={"vehicle_id": 1, "order_ids": []})
    first = manager.post("/api/admin/delivery/trips", json={"vehicle_id": 1}).get_json()
    assert first["trip"]["order_count"] == 2

    busy = manager.post("/api/admin/delivery/trips", json={"vehicle_id": 1})
    assert error_code(busy) == "VEHICLE_BUSY"


# --- Vehicle callbacks ------------------------------------------------

def dispatched_trip(customer, manager, orders=1):
    ids = [ready_order(customer, manager) for _ in range(orders)]
    trip_id = manager.post("/api/admin/delivery/trips", json={}).get_json()["trip"]["trip_id"]
    manager.post(f"/api/admin/delivery/trips/{trip_id}/dispatch")
    return trip_id, ids


def test_vehicle_must_send_its_token(client, customer, manager):
    trip_id, (order_id,) = dispatched_trip(customer, manager)
    url = f"/api/fleet/trips/{trip_id}/stops/{order_id}/completed"

    assert client.post(url).status_code == 401
    assert client.post(url, headers=bearer("wrong-token")).status_code == 401
    assert client.post(url, headers=bearer(OTHER_VEHICLE_TOKEN)).status_code == 403
    assert status_of(order_id) == "out_for_delivery"


def test_trip_completes_only_after_the_last_stop(client, customer, manager):
    trip_id, (first, second) = dispatched_trip(customer, manager, orders=2)
    done = client.post(f"/api/fleet/trips/{trip_id}/stops/{first}/completed",
                       headers=bearer(VEHICLE_TOKEN))
    assert done.get_json()["trip_status"] == "out_for_delivery"

    early = client.post(f"/api/fleet/trips/{trip_id}/status", json={"status": "completed"},
                        headers=bearer(VEHICLE_TOKEN))
    assert error_code(early) == "STOPS_OUTSTANDING"

    client.post(f"/api/fleet/trips/{trip_id}/stops/{second}/completed",
                headers=bearer(VEHICLE_TOKEN))
    again = client.post(f"/api/fleet/trips/{trip_id}/stops/{second}/completed",
                        headers=bearer(VEHICLE_TOKEN))
    assert again.get_json()["trip_status"] == "completed"       # repeat report is harmless


def test_vehicle_progress_reports_are_recorded(client, customer, manager):
    trip_id, _ = dispatched_trip(customer, manager)
    client.post(f"/api/fleet/trips/{trip_id}/status",
                json={"status": "en_route", "latitude": "37.3361", "longitude": "-121.8905"},
                headers=bearer(VEHICLE_TOKEN))

    trip = manager.get(f"/api/admin/delivery/trips/{trip_id}").get_json()["trip"]
    assert trip["last_report"] == "en_route"
    assert trip["last_position"]["latitude"] == "37.336100"


def test_manager_can_confirm_a_delivery_by_hand(customer, manager):
    trip_id, (order_id,) = dispatched_trip(customer, manager)
    response = manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": "delivered"})

    assert response.get_json()["order"]["status"] == "delivered"
    trip = manager.get(f"/api/admin/delivery/trips/{trip_id}").get_json()["trip"]
    assert trip["status"] == "completed"
