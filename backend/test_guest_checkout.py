"""Guest checkout, order placement, and order lookup integration tests.

These tests use Flask's real routes and the disposable ``ofs_test`` MySQL
database.  The payment and mapping providers are deterministic fakes.
"""

import pytest

import db as database
from conftest import APPLES_ID, CUSTOMER, error_code, requires_mysql, stock_of
from services import mapping

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

CONTACT = {
    "first_name": "Grace",
    "last_name": "Hopper",
    "email": "guest@example.com",
    "phone": "408-555-0199",
}
ADDRESS = {
    "street": "200 E Santa Clara St",
    "city": "San Jose",
    "state": "CA",
    "zip_code": "95113",
}


def add_to_guest_cart(client, quantity=2):
    response = client.post(
        "/api/cart/items", json={"product_id": APPLES_ID, "quantity": quantity})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["cart"]


def start_guest(client, contact=None, address=None):
    return client.post("/api/checkout/guest", json={
        "contact": CONTACT if contact is None else contact,
        "address": ADDRESS if address is None else address,
    })


def place_guest_order(client, *, quantity=2, token="tok_visa", key="guest-order-001"):
    add_to_guest_cart(client, quantity)
    started = start_guest(client)
    assert started.status_code == 201, started.get_json()
    address_id = started.get_json()["address"]["address_id"]
    return client.post("/api/orders", json={
        "address_id": address_id,
        "payment_token": token,
        "idempotency_key": key,
    })


def test_guest_places_an_order_end_to_end(client):
    original_stock = stock_of(APPLES_ID)
    cart = add_to_guest_cart(client, quantity=2)
    assert cart["item_count"] == 2

    estimate = client.get("/api/checkout/estimate")
    assert estimate.status_code == 200
    assert estimate.get_json()["subtotal"] == "12.98"
    assert estimate.get_json()["delivery_fee"] == "0.00"

    started = start_guest(client)
    assert started.status_code == 201
    body = started.get_json()
    assert body["user"]["is_guest"] is True
    assert body["user"]["email"] == CONTACT["email"]
    assert body["user"]["full_name"] == "Grace Hopper"
    assert body["address"]["street"] == ADDRESS["street"]

    guest = database.query_one(
        "SELECT * FROM users WHERE user_id = %s", (body["user"]["user_id"],))
    assert guest["is_guest"]
    assert guest["contact_email"] == CONTACT["email"]
    assert guest["email"].startswith("guest-")
    assert guest["email"].endswith("@guest.ofs.invalid")
    assert guest["password_hash"] == "!"

    # Starting guest checkout signs this browser into the private guest
    # account and moves its session cart into the database cart.
    moved_cart = client.get("/api/cart").get_json()["cart"]
    assert moved_cart["item_count"] == 2

    placed = client.post("/api/orders", json={
        "address_id": body["address"]["address_id"],
        "payment_token": "tok_visa",
        "idempotency_key": "guest-order-001",
    })
    assert placed.status_code == 201, placed.get_json()
    order = placed.get_json()["order"]
    assert order["status"] == "placed"
    assert order["address"]["street"] == ADDRESS["street"]
    assert order["items"][0]["quantity"] == 2
    assert order["payment"]["status"] == "approved"

    saved_order = database.query_one(
        "SELECT user_id FROM orders WHERE order_id = %s", (order["order_id"],))
    assert saved_order["user_id"] == guest["user_id"]
    assert stock_of(APPLES_ID) == original_stock - 2
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 0


def test_guest_can_look_up_the_order_after_signing_out(client):
    placed = place_guest_order(client)
    assert placed.status_code == 201
    number = placed.get_json()["order"]["order_number"]
    assert client.post("/api/auth/logout").status_code == 200

    found = client.post("/api/orders/lookup", json={
        "order_number": number.lower(),
        "email": CONTACT["email"].upper(),
    })
    assert found.status_code == 200
    assert found.get_json()["order"]["order_number"] == number
    assert found.get_json()["tracking"]["status"] == "placed"

    refused = client.post("/api/orders/lookup", json={
        "order_number": number,
        "email": "someone-else@example.com",
    })
    assert refused.status_code == 404
    assert error_code(refused) == "ORDER_NOT_FOUND"


def test_managers_see_the_guests_real_email(client, manager):
    order_id = place_guest_order(client).get_json()["order"]["order_id"]

    listed = manager.get("/api/admin/orders").get_json()["orders"][0]
    assert listed["customer_email"] == CONTACT["email"]
    assert listed["is_guest"] is True

    customer = manager.get(f"/api/admin/orders/{order_id}").get_json()["order"]["customer"]
    assert customer["email"] == CONTACT["email"]
    assert customer["is_guest"] is True


def test_guest_contact_email_cannot_be_used_to_sign_in(client):
    add_to_guest_cart(client)
    assert start_guest(client).status_code == 201
    assert client.post("/api/auth/logout").status_code == 200

    response = client.post("/api/auth/login", json={
        "email": CONTACT["email"],
        "password": "any-password",
    })
    assert response.status_code == 401
    assert error_code(response) == "INVALID_CREDENTIALS"


def test_registered_email_requires_sign_in_and_preserves_the_cart(client):
    add_to_guest_cart(client)
    before = database.query_one("SELECT COUNT(*) AS count FROM users")["count"]
    response = start_guest(client, contact={**CONTACT, "email": CUSTOMER[0]})

    assert response.status_code == 409
    assert error_code(response) == "ACCOUNT_EXISTS"
    assert database.query_one("SELECT COUNT(*) AS count FROM users")["count"] == before
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 2


@pytest.mark.parametrize("contact,code", [
    ({**CONTACT, "first_name": " "}, "BAD_REQUEST"),
    ({**CONTACT, "email": "not-an-email"}, "INVALID_EMAIL"),
    ({**CONTACT, "phone": "123"}, "INVALID_PHONE"),
])
def test_invalid_guest_contact_creates_nothing(client, contact, code):
    before = database.query_one("SELECT COUNT(*) AS count FROM users")["count"]
    response = start_guest(client, contact=contact)

    assert response.status_code == 400
    assert error_code(response) == code
    assert database.query_one("SELECT COUNT(*) AS count FROM users")["count"] == before


def test_unfindable_guest_address_creates_nothing(client):
    before = database.query_one("SELECT COUNT(*) AS count FROM users")["count"]
    response = start_guest(client, address={**ADDRESS, "street": "1 Nowhere Lane"})

    assert response.status_code == 422
    assert error_code(response) == "ADDRESS_NOT_FOUND"
    assert database.query_one("SELECT COUNT(*) AS count FROM users")["count"] == before


def test_mapping_outage_creates_no_guest_account(client):
    class UnavailableMap(mapping.FakeMapProvider):
        def geocode(self, street, city, state, zip_code):
            raise mapping.MappingError("Simulated mapping outage")

    mapping.use_provider(UnavailableMap())
    before = database.query_one("SELECT COUNT(*) AS count FROM users")["count"]
    response = start_guest(client)

    assert response.status_code == 503
    assert error_code(response) == "MAPPING_UNAVAILABLE"
    assert database.query_one("SELECT COUNT(*) AS count FROM users")["count"] == before


def test_signed_in_customer_cannot_start_guest_checkout(customer):
    response = start_guest(customer)
    assert response.status_code == 409
    assert error_code(response) == "ALREADY_SIGNED_IN"


def test_guest_can_retry_a_declined_payment_without_losing_the_cart(client):
    add_to_guest_cart(client)
    started = start_guest(client)
    address_id = started.get_json()["address"]["address_id"]
    request = {
        "address_id": address_id,
        "payment_token": "tok_chargeDeclined",
        "idempotency_key": "guest-retry-001",
    }

    declined = client.post("/api/orders", json=request)
    assert declined.status_code == 402
    assert error_code(declined) == "PAYMENT_DECLINED"
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 2

    approved = client.post(
        "/api/orders", json={**request, "payment_token": "tok_visa"})
    assert approved.status_code == 201
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 0


def test_empty_guest_cart_has_no_checkout_estimate(client):
    response = client.get("/api/checkout/estimate")
    assert response.status_code == 409
    assert error_code(response) == "CART_EMPTY"
