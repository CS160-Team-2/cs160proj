import pytest

import db as database
import ratelimit
from conftest import APPLES_ID, CUSTOMER, buy, error_code, make_product, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

LOGIN = "/api/auth/login"
RIGHT = {"email": CUSTOMER[0], "password": CUSTOMER[1]}
WRONG = {"email": CUSTOMER[0], "password": "not-the-password"}


def test_eight_wrong_passwords_make_the_ninth_try_wait(client):
    for _ in range(8):
        assert client.post(LOGIN, json=WRONG).status_code == 401

    blocked = client.post(LOGIN, json=WRONG)

    assert blocked.status_code == 429 and error_code(blocked) == "RATE_LIMITED"
    assert "wait" in blocked.get_json()["error"]["message"].lower()
    assert int(blocked.headers["Retry-After"]) > 0 and blocked.get_json()["error"]["retry_after"] > 0


def test_while_waiting_even_the_right_password_is_refused(client):
    for _ in range(8):
        client.post(LOGIN, json=WRONG)

    assert client.post(LOGIN, json=RIGHT).status_code == 429


def test_a_correct_sign_in_clears_the_count(client):
    for _ in range(7):
        client.post(LOGIN, json=WRONG)
    assert client.post(LOGIN, json=RIGHT).status_code == 200
    client.post("/api/auth/logout")

    for _ in range(7):
        assert client.post(LOGIN, json=WRONG).status_code == 401


def test_the_wait_ends_after_the_window(client, monkeypatch):
    import time
    start = time.monotonic()
    for _ in range(8):
        client.post(LOGIN, json=WRONG)
    assert client.post(LOGIN, json=RIGHT).status_code == 429

    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: start + ratelimit.WINDOW + 5)

    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_one_account_being_guessed_does_not_block_another(client):
    for _ in range(8):
        client.post(LOGIN, json=WRONG)

    other = client.post(LOGIN, json={"email": "employee@ofs.test", "password": "employee-pass-1"})

    assert other.status_code == 200


def test_an_unknown_email_is_counted_like_a_known_one(client):
    ghost = {"email": "nobody@example.com", "password": "whatever-123"}
    for _ in range(8):
        assert client.post(LOGIN, json=ghost).status_code == 401

    assert client.post(LOGIN, json=ghost).status_code == 429


def test_one_connection_trying_many_emails_is_stopped_too(client):
    for number in range(30):
        client.post(LOGIN, json={"email": f"person{number}@example.com", "password": "guess-guess-1"})

    assert client.post(LOGIN, json=RIGHT).status_code == 429


def test_the_wrong_email_and_the_wrong_password_look_the_same(client):
    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": "x" * 12})
    wrong = client.post(LOGIN, json=WRONG)

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json() == wrong.get_json()


def test_the_limits_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")
    for _ in range(12):
        client.post(LOGIN, json=WRONG)

    assert client.post(LOGIN, json=RIGHT).status_code == 200


def test_ten_look_ups_that_find_nothing_make_the_next_one_wait(client):
    guess = {"order_number": "OFS-NOPE00", "email": "someone@example.com"}
    for _ in range(10):
        assert client.post("/api/orders/lookup", json=guess).status_code == 404

    blocked = client.post("/api/orders/lookup", json=guess)

    assert blocked.status_code == 429 and error_code(blocked) == "RATE_LIMITED"


def test_look_ups_that_succeed_are_never_counted(customer, client):
    product_id = make_product(stock=50)
    number = buy(customer, {product_id: 1}).get_json()["order"]["order_number"]
    for _ in range(25):
        assert client.post("/api/orders/lookup", json={"order_number": number, "email": CUSTOMER[0]}).status_code == 200


def test_wrong_current_passwords_are_limited_when_changing_the_password(customer):
    for _ in range(5):
        assert customer.patch("/api/users/me", json={"new_password": "brand-new-pass1", "current_password": "wrong"}).status_code == 403

    blocked = customer.patch("/api/users/me", json={"new_password": "brand-new-pass1", "current_password": CUSTOMER[1]})

    assert blocked.status_code == 429


def test_wrong_passwords_are_limited_when_deleting_the_account_and_the_right_one_clears_the_count(customer):
    for _ in range(4):
        assert customer.delete("/api/users/me", json={"password": "wrong"}).status_code == 403
    assert customer.patch("/api/users/me", json={"new_password": "brand-new-pass1", "current_password": CUSTOMER[1]}).status_code == 200
    for _ in range(4):
        assert customer.delete("/api/users/me", json={"password": "wrong"}).status_code == 403


def test_a_huge_password_is_refused_and_the_longest_allowed_works(client):
    base = {"email": "long@example.com", "full_name": "Long Pass"}

    assert client.post("/api/auth/register", json={**base, "password": "p" * 129}).status_code == 400
    assert client.post("/api/auth/register", json={**base, "password": "p" * 128}).status_code == 201


def test_every_answer_has_safe_headers(client):
    response = client.get("/api/products")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.mimetype == "application/json"


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/cart", "/api/orders", "/api/users/me/addresses", "/api/admin/orders"])
def test_private_answers_are_never_cached(customer, path):
    assert customer.get(path).headers["Cache-Control"] == "no-store"


def test_the_public_shop_can_still_be_cached_by_the_browser(client):
    assert "no-store" not in client.get("/api/products").headers.get("Cache-Control", "")


def test_the_session_cookie_is_http_only_and_same_site(client):
    cookie = client.post(LOGIN, json=RIGHT).headers.get("Set-Cookie", "")

    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_https_without_a_real_secret_key_refuses_to_start(monkeypatch):
    import app as app_module
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        app_module.create_app()


PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "\"><svg onload=alert(1)>",
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "\" OR \"\"=\"",
    "%27%20OR%201%3D1",
    "Robert'); DELETE FROM orders;--",
    "{{7*7}} ${7*7}",
    "‮ reversed \u0000 nul",
    "a" * 50,
]


# How many rows the important tables have, to prove no payload deleted or added anything.
def table_sizes():
    return {t: database.query_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in ("users", "products", "orders", "addresses")}


@pytest.mark.parametrize("payload", PAYLOADS)
def test_a_hostile_name_is_kept_as_plain_text_and_never_changes_the_data(app, payload):
    before = table_sizes()
    visitor = app.test_client()

    register = visitor.post("/api/auth/register", json={"email": "hostile@example.com", "password": "longenough1", "full_name": payload[:120]})
    assert register.status_code in (201, 400)
    if register.status_code == 201:
        assert visitor.get("/api/auth/me").get_json()["user"]["full_name"] == payload[:120]
        edited = visitor.patch("/api/users/me", json={"full_name": payload[:120], "phone": payload[:30]})
        assert edited.status_code == 200 and edited.mimetype == "application/json"

    after = table_sizes()
    assert after["products"] == before["products"] and after["orders"] == before["orders"]
    assert after["users"] <= before["users"] + 1


@pytest.mark.parametrize("payload", PAYLOADS)
def test_hostile_text_in_sign_in_and_order_look_up_is_just_a_refusal(client, payload):
    before = table_sizes()

    assert client.post(LOGIN, json={"email": payload, "password": payload}).status_code == 401
    assert client.post("/api/orders/lookup", json={"order_number": payload[:20], "email": payload}).status_code in (400, 404)
    assert client.get(f"/api/orders/{payload}").status_code in (401, 404)

    assert table_sizes() == before


@pytest.mark.parametrize("payload", PAYLOADS)
def test_hostile_search_text_finds_nothing_extra_and_breaks_nothing(client, payload):
    everything = len(client.get("/api/products").get_json()["products"])

    response = client.get("/api/products", query_string={"search": payload})

    assert response.status_code == 200
    assert len(response.get_json()["products"]) < everything
    assert len(client.get("/api/products").get_json()["products"]) == everything


@pytest.mark.parametrize("payload", PAYLOADS)
def test_hostile_text_in_an_address_is_refused_or_kept_as_text(customer, payload):
    response = customer.post("/api/users/me/addresses", json={"street": payload, "city": payload[:20], "state": "CA", "zip_code": "95192"})

    assert response.status_code in (201, 400, 422)
    if response.status_code == 201:
        assert response.get_json()["address"]["street"] == payload
    assert customer.get("/api/users/me/addresses").status_code == 200


@pytest.mark.parametrize("payload", PAYLOADS)
def test_hostile_text_in_guest_checkout_never_creates_anything_unsafe(client, payload):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    before = table_sizes()

    response = client.post("/api/checkout/guest", json={
        "contact": {"first_name": payload[:40], "last_name": payload[:40], "email": "guest@example.com", "phone": "408-555-0100"},
        "address": {"street": "200 E Santa Clara St", "city": "San Jose", "state": "CA", "zip_code": "95113"}})

    assert response.status_code in (201, 400)
    assert response.mimetype == "application/json"
    assert table_sizes()["orders"] == before["orders"] and table_sizes()["products"] == before["products"]


def test_a_hostile_name_comes_back_exactly_as_typed_in_an_order(customer, manager):
    payload = "<img src=x onerror=alert(1)>"
    customer.patch("/api/users/me", json={"full_name": payload})
    product_id = make_product(stock=10)
    buy(customer, {product_id: 1})

    orders = manager.get("/api/admin/orders").get_json()["orders"]

    assert orders[0]["customer_name"] == payload and manager.get("/api/admin/orders").mimetype == "application/json"
