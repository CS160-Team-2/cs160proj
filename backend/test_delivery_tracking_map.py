"""Customer-facing delivery map integration tests."""

from urllib.parse import parse_qs, urlparse

import pytest

import db as database
from conftest import VEHICLE_TOKEN, ready_order, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def order_number(order_id):
    return database.query_one(
        "SELECT order_number FROM orders WHERE order_id = %s", (order_id,)
    )["order_number"]


def test_planned_trip_exposes_only_this_customers_map_data(customer, manager):
    order_id = ready_order(customer, manager, weight="4.00")
    number = order_number(order_id)
    created = manager.post(
        "/api/admin/delivery/trips", json={"order_ids": [order_id]})
    assert created.status_code == 201, created.get_json()

    response = customer.get(f"/api/orders/{number}/tracking")
    assert response.status_code == 200
    tracking = response.get_json()
    tracking_map = tracking["map"]

    assert tracking_map["provider"] == "fake"
    assert tracking_map["trip_status"] == "planned"
    assert tracking_map["store"] == {
        "latitude": "37.335200", "longitude": "-121.881100"}
    assert tracking_map["destination"] == {
        "latitude": "37.335200", "longitude": "-121.881100"}
    assert tracking_map["vehicle_position"] is None
    assert tracking_map["last_report"] is None
    assert tracking_map["last_updated"] is None
    # The customer receives their destination and the vehicle's latest
    # position, never another customer's stops or the manager's full trip.
    assert "path" not in tracking_map
    assert "stops" not in tracking_map

    query = parse_qs(urlparse(tracking_map["directions_url"]).query)
    assert query["api"] == ["1"]
    assert query["destination"] == ["37.335200,-121.881100"]


def test_vehicle_location_report_appears_on_customer_tracking(client, customer, manager):
    order_id = ready_order(customer, manager, weight="4.00")
    number = order_number(order_id)
    trip = manager.post(
        "/api/admin/delivery/trips", json={"order_ids": [order_id]}
    ).get_json()["trip"]
    dispatched = manager.post(
        f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    assert dispatched.status_code == 200

    reported = client.post(
        f"/api/fleet/trips/{trip['trip_id']}/status",
        json={
            "status": "en_route",
            "latitude": "37.336100",
            "longitude": "-121.890500",
        },
        headers=bearer(VEHICLE_TOKEN),
    )
    assert reported.status_code == 200

    tracking = customer.get(f"/api/orders/{number}/tracking").get_json()
    tracking_map = tracking["map"]
    assert tracking_map["trip_status"] == "out_for_delivery"
    assert tracking_map["last_report"] == "en_route"
    assert tracking_map["last_updated"] is not None
    assert tracking_map["vehicle_position"] == {
        "latitude": "37.336100",
        "longitude": "-121.890500",
    }

    query = parse_qs(urlparse(tracking_map["directions_url"]).query)
    assert query["origin"] == ["37.336100,-121.890500"]
    assert query["destination"] == ["37.335200,-121.881100"]
