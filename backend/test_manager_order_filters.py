"""M2-M4: manager search/date filtering and safe payment history lookup."""
import pytest

import db as database
from conftest import (APPLES_ID, CUSTOMER_ADDRESS_ID, buy, new_key,
                      requires_mysql)

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def placed_order(customer):
    response = buy(customer, {APPLES_ID: 1})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["order"]


def find_orders(manager, **filters):
    response = manager.get("/api/admin/orders", query_string=filters)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["orders"]


def place_guest_order(client, *, first_name="Grace", email="visitor@example.com"):
    added = client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    assert added.status_code == 201
    started = client.post("/api/checkout/guest", json={
        "contact": {"first_name": first_name, "last_name": "Guest", "email": email,
                    "phone": "408-555-0199"},
        "address": {"street": "200 E Santa Clara St", "city": "San Jose",
                    "state": "CA", "zip_code": "95113"},
    })
    assert started.status_code == 201, started.get_json()
    response = client.post("/api/orders", json={
        "address_id": started.get_json()["address"]["address_id"],
        "payment_token": "tok_visa", "idempotency_key": new_key(),
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["order"]


def test_date_bounds_include_the_whole_day(customer, manager):
    orders = [placed_order(customer) for _ in range(4)]
    dates = ["2026-11-03 23:59:59", "2026-11-04 00:00:00",
             "2026-11-04 23:59:59", "2026-11-05 00:00:00"]
    with database.transaction() as cur:
        for order, placed_at in zip(orders, dates):
            cur.execute("UPDATE orders SET placed_at = %s WHERE order_id = %s",
                        (placed_at, order["order_id"]))

    found = find_orders(manager, **{"from": "2026-11-04", "to": "2026-11-04"})
    assert {order["order_id"] for order in found} == {
        orders[1]["order_id"], orders[2]["order_id"]}
    assert [order["order_id"] for order in find_orders(manager, to="2026-11-03")] == [
        orders[0]["order_id"]]
    assert [order["order_id"] for order in find_orders(manager, **{"from": "2026-11-05"})] == [
        orders[3]["order_id"]]


def test_search_status_and_date_filters_work_together(customer, manager):
    first, second, outside = [placed_order(customer) for _ in range(3)]
    with database.transaction() as cur:
        cur.execute("UPDATE orders SET placed_at = '2026-11-04 12:00:00'")
        cur.execute("UPDATE orders SET placed_at = '2026-11-03 12:00:00' WHERE order_id = %s",
                    (outside["order_id"],))
    for order in (first, outside):
        assert manager.patch(f"/api/admin/orders/{order['order_id']}/status",
                             json={"status": "awaiting_delivery"}).status_code == 200

    found = find_orders(manager, q="customer@ofs.test", status="awaiting_delivery",
                        **{"from": "2026-11-04", "to": "2026-11-04"})
    assert [order["order_id"] for order in found] == [first["order_id"]]
    assert find_orders(manager, q=second["order_number"], status="awaiting_delivery",
                       **{"from": "2026-11-04", "to": "2026-11-04"}) == []


@pytest.mark.parametrize("filters", [
    {"from": "not-a-date"}, {"to": "2026-02-30"},
    {"from": "2026-11-05", "to": "2026-11-04"},
])
def test_invalid_or_reversed_dates_are_rejected(manager, filters):
    response = manager.get("/api/admin/orders", query_string=filters)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_maximum_to_date_does_not_overflow(customer, manager):
    order = placed_order(customer)
    found = find_orders(manager, to="9999-12-31")
    assert [row["order_id"] for row in found] == [order["order_id"]]


@pytest.mark.parametrize("field", ["number", "name", "email"])
def test_search_finds_order_number_customer_name_or_email(customer, manager, field):
    order = placed_order(customer)
    query = {"number": order["order_number"].lower(), "name": "  ANNA RIVERA  ",
             "email": "CUSTOMER@OFS.TEST"}[field]
    found = find_orders(manager, q=query)
    assert [row["order_id"] for row in found] == [order["order_id"]]


def test_search_uses_guest_contact_email_not_the_private_placeholder(client, manager):
    order = place_guest_order(client)
    found = find_orders(manager, q="VISITOR@EXAMPLE.COM")
    assert [row["order_id"] for row in found] == [order["order_id"]]
    assert found[0]["customer_email"] == "visitor@example.com"
    placeholder = database.query_one("SELECT email FROM users WHERE is_guest = TRUE")["email"]
    assert find_orders(manager, q=placeholder) == []


def test_percent_underscore_and_escape_characters_are_literal_searches(customer, client, manager):
    placed_order(customer)
    guest = place_guest_order(client, first_name="Rate%_!Team")
    for query in ("%", "_", "!", "%_!"):
        found = find_orders(manager, q=query)
        assert [row["order_id"] for row in found] == [guest["order_id"]]


def test_quote_in_search_is_data_not_sql(customer, manager):
    placed_order(customer)
    assert find_orders(manager, q="%' OR 1=1 --") == []
    assert len(find_orders(manager)) == 1


def test_order_number_lookup_exposes_both_attempts_with_only_safe_payment_fields(customer, manager):
    key = new_key()
    declined = buy(customer, {APPLES_ID: 1}, token="tok_declined", key=key)
    assert declined.status_code == 402
    approved = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa", "idempotency_key": key})
    assert approved.status_code == 201
    number = approved.get_json()["order"]["order_number"]
    found = find_orders(manager, q=number)
    assert len(found) == 1
    response = manager.get(f"/api/admin/orders/{found[0]['order_id']}/payments")
    assert response.status_code == 200
    attempts = response.get_json()["payments"]
    assert [attempt["status"] for attempt in attempts] == ["declined", "approved"]
    safe_fields = {"transaction_id", "amount", "status", "gateway_ref", "card_last4",
                   "failure_reason", "created_at"}
    for attempt in attempts:
        assert set(attempt) == safe_fields
        assert attempt["transaction_id"] > 0
        assert isinstance(attempt["amount"], str)
        assert len(attempt["card_last4"]) == 4
        assert attempt["created_at"]
    assert attempts[0]["failure_reason"]


def test_payment_history_and_filtered_orders_remain_manager_only(customer, employee, client):
    order = placed_order(customer)
    for outsider, expected in ((customer, 403), (employee, 403), (client, 401)):
        assert outsider.get(f"/api/admin/orders/{order['order_id']}/payments").status_code == expected
        assert outsider.get("/api/admin/orders?q=Anna&from=2026-11-04").status_code == expected
