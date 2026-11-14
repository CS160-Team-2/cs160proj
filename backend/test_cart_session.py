"""How long a shopper's cart and sign-in last (customer backlog C3).

A guest's cart is kept in the session cookie. It must outlive the browser
window for about two weeks, and every visit pushes the expiry forward.
Staff sessions stay browser-session cookies.
"""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import APPLES_ID, CUSTOMER, EMPLOYEE, MANAGER, requires_mysql, signed_in

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


# Returns when the test client's session cookie expires, or None.
def _expires(test_client):
    cookie = test_client.get_cookie("session")
    return cookie.expires if cookie else None


# Returns how many days the session cookie still has left.
def _days_left(test_client):
    expires = _expires(test_client)
    assert expires is not None, "the session cookie has no expiry"
    return (expires - datetime.now(timezone.utc)).total_seconds() / 86400


# A guest's first cart item gives the cookie a 14-day life.
def test_guest_cart_cookie_lasts_about_two_weeks(client):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 2})

    assert 13 < _days_left(client) <= 14


# Repeated visits with the same cookie keep showing the cart.
def test_guest_cart_is_still_there_on_the_next_visit(client):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 2})

    for _ in range(3):
        cart = client.get("/api/cart").get_json()["cart"]
        assert cart["item_count"] == 2


# A visit pushes a nearly expired cookie back out to 14 days.
def test_each_visit_extends_the_expiry(client, app):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    old_expiry = datetime.now(timezone.utc) + timedelta(days=3)
    cookie = client.get_cookie("session")
    client.delete_cookie("session")
    client.set_cookie("session", cookie.value, expires=old_expiry)

    response = client.get("/api/cart")

    assert response.get_json()["cart"]["item_count"] == 1
    assert any(h.startswith("session=") for h in response.headers.getlist("Set-Cookie"))
    assert _days_left(client) > 13


# Removing an item also leaves the cookie persistent.
def test_removing_a_guest_item_keeps_the_cookie_lasting(client):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    client.delete(f"/api/cart/items/{APPLES_ID}")

    assert 13 < _days_left(client) <= 14


# A customer's sign-in cookie lasts 14 days.
def test_signed_in_customer_stays_signed_in_for_two_weeks(app):
    customer = signed_in(app, *CUSTOMER)

    assert 13 < _days_left(customer) <= 14


# Employee and manager cookies have no expiry.
@pytest.mark.parametrize("account", [EMPLOYEE, MANAGER])
def test_staff_sessions_end_with_the_browser(app, account):
    staff = signed_in(app, *account)

    assert _expires(staff) is None


# Signing in keeps the guest cart; signing out ends the session.
def test_guest_cart_survives_signing_in_and_signing_out_clears_the_session(app):
    visitor = app.test_client()
    visitor.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 2})
    visitor.post("/api/auth/login", json={"email": CUSTOMER[0], "password": CUSTOMER[1]})

    assert visitor.get("/api/cart").get_json()["cart"]["item_count"] >= 2
    assert 13 < _days_left(visitor) <= 14

    visitor.post("/api/auth/logout")
    assert visitor.get("/api/cart").get_json()["cart"]["item_count"] == 0
    assert visitor.get("/api/auth/me").status_code == 401


# The 14-day default comes from CART_SESSION_DAYS.
def test_the_lifetime_comes_from_the_setting(app):
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=14)


# Signs in as the seeded customer with a "Remember me" choice and returns the client.
def _login_with(app, remember):
    client = app.test_client()
    payload = {"email": CUSTOMER[0], "password": CUSTOMER[1]}
    if remember is not None:
        payload["remember"] = remember
    assert client.post("/api/auth/login", json=payload).status_code == 200
    return client


# Remember me ticked (or not mentioned) gives the 14-day cookie.
@pytest.mark.parametrize("remember", [True, None])
def test_remember_me_keeps_the_sign_in_for_two_weeks(app, remember):
    assert 13 < _days_left(_login_with(app, remember)) <= 14


# Remember me unticked gives a cookie that ends with the browser, yet the customer stays signed in meanwhile.
def test_without_remember_me_the_sign_in_ends_with_the_browser(app):
    customer = _login_with(app, False)

    assert _expires(customer) is None
    assert customer.get("/api/auth/me").status_code == 200
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    assert _expires(customer) is None


# Registering follows the same choice.
@pytest.mark.parametrize("remember, persistent", [(False, False), (True, True)])
def test_registering_follows_the_remember_choice(app, remember, persistent):
    client = app.test_client()
    response = client.post("/api/auth/register", json={
        "email": "new@example.com", "password": "long-enough-1", "full_name": "New", "remember": remember})
    assert response.status_code == 201
    assert (_expires(client) is not None) is persistent


# A guest's cart keeps its 14 days even though the later sign-in was not remembered.
def test_a_guest_cart_still_lasts_two_weeks_before_signing_in(app):
    visitor = app.test_client()
    visitor.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    assert 13 < _days_left(visitor) <= 14

    visitor.post("/api/auth/login", json={"email": CUSTOMER[0], "password": CUSTOMER[1], "remember": False})
    assert _expires(visitor) is None
    assert visitor.get("/api/cart").get_json()["cart"]["item_count"] >= 1


# Staff stay browser-session whatever the box says.
def test_staff_ignore_remember_me(app):
    client = app.test_client()
    client.post("/api/auth/login", json={"email": MANAGER[0], "password": MANAGER[1], "remember": True})
    assert _expires(client) is None
