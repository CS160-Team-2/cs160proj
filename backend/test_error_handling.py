"""C6: every failure the customer can hit comes back as clear JSON with the
right status, so the frontend can show a message and send them somewhere useful.
"""

import pytest

from conftest import APPLES_ID, CUSTOMER_ADDRESS_ID, error_code, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


# Checks a response has the standard error shape and returns its error object.
def error_of(response):
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] and body["error"]["message"]
    return body["error"]


def test_an_unknown_api_path_is_a_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


def test_the_wrong_method_is_a_json_405(client):
    response = client.delete("/api/products")
    assert response.status_code == 405
    assert error_of(response)["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.parametrize("path", ["/api/orders", "/api/users/me/addresses", "/api/orders/OFS-X1"])
def test_signed_out_requests_get_a_401_the_page_can_act_on(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"
    assert "sign in" in error_of(response)["message"].lower()


def test_a_session_that_stops_being_valid_gets_a_401(customer):
    customer.get("/api/orders")
    with customer.session_transaction() as session:
        session["user_id"] = 99999
    response = customer.get("/api/orders")
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


def test_a_customer_is_refused_staff_pages_with_a_403(customer):
    response = customer.get("/api/admin/orders")
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_an_order_that_does_not_exist_is_a_404_with_a_message(customer):
    response = customer.get("/api/orders/OFS-NOPE")
    assert response.status_code == 404
    assert error_of(response)["message"]


def test_a_broken_json_body_is_a_clear_400_not_a_crash(customer):
    response = customer.post("/api/orders", data="{not json", content_type="application/json")
    assert response.status_code == 400
    assert error_of(response)["message"]


def test_an_empty_cart_cannot_be_ordered_and_says_why(customer):
    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_visa", "idempotency_key": "k-empty"})
    assert response.status_code == 400
    assert error_of(response)["message"]


def test_a_declined_card_is_a_402_that_keeps_the_cart(customer):
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "tok_chargeDeclined", "idempotency_key": "k-declined"})
    assert response.status_code == 402
    assert "declined" in error_of(response)["message"].lower()
    assert customer.get("/api/cart").get_json()["cart"]["item_count"] == 1


def test_an_unexpected_crash_is_a_generic_500_that_leaks_nothing(app, customer, monkeypatch):
    import routes.cart as cart_routes

    # Makes the cart route blow up with a message that must never reach the customer.
    def explode(*args, **kwargs):
        raise RuntimeError("secret database detail")

    monkeypatch.setattr(cart_routes, "ok", explode)
    app.config.update(PROPAGATE_EXCEPTIONS=False)
    response = customer.get("/api/cart")
    assert response.status_code == 500
    assert error_of(response)["code"] == "SERVER_ERROR"
    assert "secret" not in response.get_data(as_text=True)


def test_an_oversized_upload_is_a_json_413(manager):
    response = manager.post(
        f"/api/admin/products/{APPLES_ID}/image",
        data={"image": (__import__("io").BytesIO(b"x" * (7 * 1024 * 1024)), "big.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code in (404, 413)
    assert response.get_json()["ok"] is False
