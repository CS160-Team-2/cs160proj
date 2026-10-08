"""Checkout, payment and orders (API tables VI and VII; backlog B-09;
test plan T-08 and T-10)."""

import threading
from decimal import Decimal

import pytest

import db as database
from conftest import (APPLES_ID, CUSTOMER_ADDRESS_ID, buy, error_code, make_product,
                      new_key, requires_mysql, stock_of)
from services import payments

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def cart_count(client):
    return client.get("/api/cart").get_json()["cart"]["item_count"]


# --- Preview ----------------------------------------------------------

def test_preview_shows_the_full_breakdown_and_changes_nothing(customer):
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 7})  # 21 lb
    response = customer.post("/api/checkout/preview", json={"address_id": CUSTOMER_ADDRESS_ID})

    body = response.get_json()
    assert body["subtotal"] == "45.43"
    assert body["total_weight_lb"] == "21.00"
    assert body["delivery_fee"] == "10.00"
    assert Decimal(body["grand_total"]) == (Decimal(body["subtotal"]) + Decimal(body["tax"])
                                            + Decimal(body["delivery_fee"]))
    assert stock_of(APPLES_ID) == 40 and cart_count(customer) == 7


def test_preview_refuses_an_empty_cart(customer):
    response = customer.post("/api/checkout/preview", json={"address_id": CUSTOMER_ADDRESS_ID})
    assert error_code(response) == "CART_EMPTY"


def test_preview_refuses_someone_elses_address(client):
    client.post("/api/auth/register", json={
        "email": "b@example.com", "password": "long-enough-1", "full_name": "B"})
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    response = client.post("/api/checkout/preview", json={"address_id": CUSTOMER_ADDRESS_ID})
    assert error_code(response) == "INVALID_ADDRESS"


# --- Placing an order -------------------------------------------------

def test_a_successful_order_writes_everything_together(customer):
    response = buy(customer, {APPLES_ID: 2})

    assert response.status_code == 201
    order = response.get_json()["order"]
    assert order["order_number"].startswith("OFS-")
    assert order["status"] == "placed"
    assert order["items"][0]["unit_price"] == "6.49"
    assert order["payment"]["card_last4"] == "4242"

    assert stock_of(APPLES_ID) == 38
    assert cart_count(customer) == 0
    sale = database.query_one("SELECT change_qty, reason FROM inventory_log WHERE product_id = %s",
                              (APPLES_ID,))
    assert sale["change_qty"] == -2 and order["order_number"] in sale["reason"]


def test_a_declined_card_leaves_the_cart_and_stock_alone(customer):
    response = buy(customer, {APPLES_ID: 2}, token="tok_declined")

    assert response.status_code == 402
    assert error_code(response) == "PAYMENT_DECLINED"
    assert stock_of(APPLES_ID) == 40
    assert cart_count(customer) == 2
    assert database.query_one("SELECT COUNT(*) AS n FROM orders")["n"] == 0
    attempt = database.query_one("SELECT status, order_id FROM payments")
    assert attempt["status"] == "declined" and attempt["order_id"] is None


def test_retrying_after_a_decline_links_both_attempts_to_the_order(customer, manager):
    key = new_key()
    buy(customer, {APPLES_ID: 1}, token="tok_declined", key=key)
    placed = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa", "idempotency_key": key})

    order_id = placed.get_json()["order"]["order_id"]
    attempts = manager.get(f"/api/admin/orders/{order_id}/payments").get_json()["payments"]
    assert [a["status"] for a in attempts] == ["declined", "approved"]
    assert all("card_number" not in a for a in attempts)


def test_the_same_checkout_submitted_twice_charges_once(customer):
    key = new_key()
    first = buy(customer, {APPLES_ID: 1}, key=key)
    second = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa", "idempotency_key": key})

    assert second.status_code == 200 and second.get_json()["duplicate"] is True
    assert second.get_json()["order"]["order_number"] == first.get_json()["order"]["order_number"]
    assert database.query_one("SELECT COUNT(*) AS n FROM payments")["n"] == 1


def test_gateway_outage_is_reported_and_nothing_changes(customer):
    response = buy(customer, {APPLES_ID: 1}, token="tok_gateway_down")
    assert response.status_code == 502
    assert stock_of(APPLES_ID) == 40 and cart_count(customer) == 1


def test_a_failure_after_charging_refunds_the_card(customer, monkeypatch):
    gateway = payments.gateway()
    original_clear = __import__("routes.cart", fromlist=["clear"]).clear

    def broken_clear(cur, user_id):
        raise RuntimeError("database fell over")
    monkeypatch.setattr("routes.cart.clear", broken_clear)

    response = buy(customer, {APPLES_ID: 1})
    monkeypatch.setattr("routes.cart.clear", original_clear)

    assert response.status_code == 500
    assert len(gateway.refunds) == 1
    assert stock_of(APPLES_ID) == 40
    assert database.query_one("SELECT COUNT(*) AS n FROM orders")["n"] == 0
    assert database.query_one("SELECT status FROM payments")["status"] == "refunded"


def test_stock_that_ran_out_since_adding_to_cart_blocks_checkout(customer):
    product_id = make_product(stock=2)
    customer.post("/api/cart/items", json={"product_id": product_id, "quantity": 2})
    with database.transaction() as cur:
        cur.execute("UPDATE inventory SET quantity_in_stock = 1 WHERE product_id = %s",
                    (product_id,))

    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa",
        "idempotency_key": new_key()})
    assert error_code(response) == "CART_NEEDS_CHANGES"
    assert response.get_json()["error"]["items"][0]["product_id"] == product_id


def test_two_customers_racing_for_the_last_unit(app, customer):
    """T-08: exactly one of two simultaneous checkouts gets the last item."""
    product_id = make_product(stock=1)
    rival = app.test_client()
    rival.post("/api/auth/register", json={
        "email": "rival@example.com", "password": "long-enough-1", "full_name": "Rival"})
    rival_address = rival.post("/api/users/me/addresses", json={
        "street": "10 Market St", "city": "San Jose", "state": "CA", "zip_code": "95113",
    }).get_json()["address"]["address_id"]

    for shopper in (customer, rival):
        shopper.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})

    results = {}

    def checkout(name, shopper, address_id):
        results[name] = shopper.post("/api/orders", json={
            "address_id": address_id, "payment_token": "tok_visa",
            "idempotency_key": new_key()}).status_code

    threads = [threading.Thread(target=checkout, args=("a", customer, CUSTOMER_ADDRESS_ID)),
               threading.Thread(target=checkout, args=("b", rival, rival_address))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == [201, 409]
    assert stock_of(product_id) == 0


def test_idempotency_key_is_required(customer):
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa"})
    assert error_code(response) == "MISSING_IDEMPOTENCY_KEY"


# --- After the order --------------------------------------------------

def test_order_history_and_detail(customer):
    number = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_number"]

    history = customer.get("/api/orders").get_json()["orders"]
    assert [o["order_number"] for o in history] == [number]
    assert customer.get(f"/api/orders/{number}").get_json()["order"]["items"][0]["quantity"] == 1


def test_a_later_price_change_does_not_rewrite_an_order(customer, employee):
    number = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_number"]
    employee.patch(f"/api/admin/products/{APPLES_ID}", json={"price": "99.00", "name": "Renamed"})

    item = customer.get(f"/api/orders/{number}").get_json()["order"]["items"][0]
    assert item["unit_price"] == "6.49" and item["name"] == "Organic Apples, 3 lb bag"


def test_customers_cannot_see_each_others_orders(app, customer):
    number = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_number"]
    other = app.test_client()
    other.post("/api/auth/register", json={
        "email": "c@example.com", "password": "long-enough-1", "full_name": "C"})
    assert other.get(f"/api/orders/{number}").status_code == 404
    assert other.get(f"/api/orders/{number}/tracking").status_code == 404


def test_tracking_starts_at_placed(customer):
    number = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_number"]
    tracking = customer.get(f"/api/orders/{number}/tracking").get_json()

    assert tracking["status"] == "placed"
    assert [s["done"] for s in tracking["steps"]] == [True, False, False, False, False]
    assert tracking["estimated_arrival"] is None


# --- Manager order monitor --------------------------------------------

def test_manager_filters_orders_by_status(customer, manager):
    buy(customer, {APPLES_ID: 1})
    assert len(manager.get("/api/admin/orders?status=placed").get_json()["orders"]) == 1
    assert manager.get("/api/admin/orders?status=delivered").get_json()["orders"] == []
    assert manager.get("/api/admin/orders?status=lost").status_code == 400


def test_status_moves_forward_and_records_who(customer, manager):
    order_id = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_id"]
    manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": "awaiting_delivery"})

    history = manager.get(f"/api/admin/orders/{order_id}").get_json()["order"]["history"]
    assert history[-1]["to_status"] == "awaiting_delivery"
    assert history[-1]["changed_by"] == "Maya Chen"


@pytest.mark.parametrize("status,code", [
    ("delivered", "INVALID_STATUS_CHANGE"),      # skipping
    ("placed", "INVALID_STATUS_CHANGE"),         # standing still
])
def test_status_cannot_skip(customer, manager, status, code):
    order_id = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_id"]
    response = manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": status})
    assert error_code(response) == code


def test_status_cannot_go_backwards(customer, manager):
    order_id = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_id"]
    manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": "awaiting_delivery"})
    response = manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": "placed"})
    assert error_code(response) == "INVALID_STATUS_CHANGE"


def test_trip_statuses_must_come_from_the_delivery_screens(customer, manager):
    order_id = buy(customer, {APPLES_ID: 1}).get_json()["order"]["order_id"]
    manager.patch(f"/api/admin/orders/{order_id}/status", json={"status": "awaiting_delivery"})
    response = manager.patch(f"/api/admin/orders/{order_id}/status",
                             json={"status": "assigned_to_trip"})
    assert error_code(response) == "USE_DELIVERY_ENDPOINTS"
