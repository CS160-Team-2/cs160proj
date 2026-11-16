"""C14: address-only previews through the real tracking/lookup API."""

import pytest

import db as database
from conftest import APPLES_ID, CUSTOMER, CUSTOMER_ADDRESS_ID, buy, ready_order, requires_mysql
from services import mapping

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def placed_order(customer):
    response = buy(customer, {APPLES_ID: 1})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["order"]


def tracking(customer, number):
    response = customer.get(f"/api/orders/{number}/tracking")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def assert_preview(data):
    preview = data["map"]
    assert preview["preview"] is True
    assert preview["store"] is not None
    assert preview["destination"] is not None
    assert preview["directions_url"] is None
    assert preview["vehicle_position"] is None
    assert preview["vehicle_mode"] is None
    assert preview["last_report"] is None
    assert preview["last_updated"] is None
    assert preview["provider"] is None
    assert data["estimated_arrival"] is None
    assert "path" not in preview
    assert "stops" not in preview
    return preview


@pytest.mark.parametrize("ready", [False, True], ids=["placed", "awaiting-delivery"])
def test_order_has_an_address_preview_before_assignment(customer, manager, ready):
    order = placed_order(customer)
    if ready:
        response = manager.patch(
            f"/api/admin/orders/{order['order_id']}/status",
            json={"status": "awaiting_delivery"},
        )
        assert response.status_code == 200
    data = tracking(customer, order["order_number"])
    preview = assert_preview(data)
    assert preview["trip_status"] is None
    assert preview["destination"] == {
        "latitude": order["address"]["latitude"],
        "longitude": order["address"]["longitude"],
    }
    assert data["status"] == ("awaiting_delivery" if ready else "placed")
    assert data["steps"][0]["done"] is True


def test_preview_uses_paid_order_address_after_saved_address_is_edited(customer):
    order = placed_order(customer)
    changed = customer.patch(
        f"/api/users/me/addresses/{CUSTOMER_ADDRESS_ID}",
        json={"street": "200 E Santa Clara St", "zip_code": "95113"},
    )
    assert changed.status_code == 200, changed.get_json()
    assert changed.get_json()["address"]["address_id"] != order["address"]["address_id"]
    preview = assert_preview(tracking(customer, order["order_number"]))
    assert preview["destination"] == {
        "latitude": order["address"]["latitude"],
        "longitude": order["address"]["longitude"],
    }


def test_preview_uses_configured_store_without_calling_a_mapping_service(customer, monkeypatch):
    order = placed_order(customer)
    monkeypatch.setenv("STORE_LATITUDE", "37.350000")
    monkeypatch.setenv("STORE_LONGITUDE", "-121.900000")

    def unexpected_provider():
        pytest.fail("A preview must not geocode or plan routes")

    monkeypatch.setattr(mapping, "provider", unexpected_provider)
    preview = assert_preview(tracking(customer, order["order_number"]))
    assert preview["store"] == {"latitude": "37.350000", "longitude": "-121.900000"}


def test_guest_can_preview_after_logout_using_order_number_and_email(client):
    assert client.post("/api/cart/items", json={
        "product_id": APPLES_ID, "quantity": 1,
    }).status_code == 201
    started = client.post("/api/checkout/guest", json={
        "contact": {
            "first_name": "Preview", "last_name": "Guest",
            "email": "c14-guest@example.com", "phone": "408-555-0199",
        },
        "address": {
            "street": "200 E Santa Clara St", "city": "San Jose",
            "state": "CA", "zip_code": "95113",
        },
    })
    assert started.status_code == 201, started.get_json()
    address = started.get_json()["address"]
    placed = client.post("/api/orders", json={
        "address_id": address["address_id"], "payment_token": "tok_visa",
        "idempotency_key": "c14-guest-order",
    })
    assert placed.status_code == 201, placed.get_json()
    number = placed.get_json()["order"]["order_number"]
    assert client.post("/api/auth/logout").status_code == 200
    found = client.post("/api/orders/lookup", json={
        "order_number": number, "email": "c14-guest@example.com",
    })
    assert found.status_code == 200, found.get_json()
    preview = assert_preview(found.get_json()["tracking"])
    assert preview["destination"] == {
        "latitude": address["latitude"], "longitude": address["longitude"],
    }


def test_other_customers_and_signed_out_visitors_cannot_read_the_preview(customer, client):
    order = placed_order(customer)
    path = f"/api/orders/{order['order_number']}/tracking"
    assert client.get(path).status_code == 401
    registered = client.post("/api/auth/register", json={
        "email": "c14-other@example.com", "password": "different-pass-1",
        "full_name": "Another Customer",
    })
    assert registered.status_code == 201, registered.get_json()
    refused = client.get(path)
    assert refused.status_code == 404
    assert "map" not in refused.get_json()


@pytest.mark.parametrize("wrong_number", [False, True], ids=["wrong-email", "unknown-number"])
def test_invalid_lookup_does_not_expose_coordinates(customer, client, wrong_number):
    order = placed_order(customer)
    response = client.post("/api/orders/lookup", json={
        "order_number": "OFS-UNKNOWN" if wrong_number else order["order_number"],
        "email": CUSTOMER[0] if wrong_number else "wrong@example.com",
    })
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert "tracking" not in response.get_json()
    assert "map" not in response.get_json()


def test_preview_changes_to_route_and_back_when_removed_from_a_planned_trip(customer, manager):
    order_id = ready_order(customer, manager)
    number = database.query_one(
        "SELECT order_number FROM orders WHERE order_id = %s", (order_id,),
    )["order_number"]
    before = assert_preview(tracking(customer, number))
    created = manager.post("/api/admin/delivery/trips", json={"order_ids": [order_id]})
    assert created.status_code == 201, created.get_json()
    trip_id = created.get_json()["trip"]["trip_id"]
    routed = tracking(customer, number)
    assert routed["map"]["preview"] is False
    assert routed["map"]["trip_status"] == "planned"
    assert routed["map"]["directions_url"]
    assert routed["estimated_arrival"] is not None
    assert routed["map"]["destination"] == before["destination"]

    removed = manager.delete(f"/api/admin/delivery/trips/{trip_id}/orders/{order_id}")
    assert removed.status_code == 200, removed.get_json()
    assert_preview(tracking(customer, number))


@pytest.mark.parametrize("missing", ["route_json", "route_planned_at"])
def test_assigned_order_without_a_complete_plan_shows_preview_not_a_stale_eta(customer, manager, missing):
    order_id = ready_order(customer, manager)
    created = manager.post("/api/admin/delivery/trips", json={"order_ids": [order_id]})
    assert created.status_code == 201
    trip_id = created.get_json()["trip"]["trip_id"]
    # These are fixed test-controlled column names, never request input.
    with database.transaction() as cur:
        cur.execute(f"UPDATE delivery_trips SET {missing} = NULL WHERE trip_id = %s", (trip_id,))
    number = database.query_one(
        "SELECT order_number FROM orders WHERE order_id = %s", (order_id,),
    )["order_number"]
    preview = assert_preview(tracking(customer, number))
    assert preview["trip_status"] == "planned"


def test_completed_order_without_a_route_does_not_claim_to_be_waiting_for_assignment(customer, manager):
    order_id = ready_order(customer, manager)
    created = manager.post("/api/admin/delivery/trips", json={"order_ids": [order_id]})
    assert created.status_code == 201
    trip_id = created.get_json()["trip"]["trip_id"]
    assert manager.post(f"/api/admin/delivery/trips/{trip_id}/dispatch").status_code == 200
    completed = manager.post(
        f"/api/admin/delivery/trips/{trip_id}/simulation/stops/{order_id}/complete",
        json={"confirmed": True},
    )
    assert completed.status_code == 200, completed.get_json()
    with database.transaction() as cur:
        cur.execute("UPDATE delivery_trips SET route_json = NULL WHERE trip_id = %s", (trip_id,))
    number = database.query_one(
        "SELECT order_number FROM orders WHERE order_id = %s", (order_id,),
    )["order_number"]
    data = tracking(customer, number)
    assert data["status"] == "delivered"
    assert data["map"] is None
    assert data["estimated_arrival"] is None
