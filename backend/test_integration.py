"""Feasibility tests — THIS is what pytest is for in a spike.

These tests do not check business logic. They check that the
technologies actually work together on this machine:

    Flask  <->  PyMySQL  <->  MySQL 8

Each test answers a question the team cannot answer by reading
documentation, because the answer depends on the local install, the
driver version, and the platform.

Requires MySQL running with schema.sql loaded. If it is not, every test
here is skipped with an explanation rather than failing noisily.

Run:  pytest test_integration.py -v
"""

from decimal import Decimal

from conftest import requires_mysql, LEMON_ID, APPLE_ID, WATER_ID

import db as database


# =====================================================================
# A. Connectivity — does the stack talk to itself at all?
# =====================================================================

@requires_mysql
def test_mysql_is_reachable():
    """Feasibility: can PyMySQL connect from this OS with these
    credentials? On Windows this also proves the MySQL service is
    running; on macOS, that the server was started from System Settings."""
    version = database.db_version()
    assert version.startswith("8."), f"Expected MySQL 8.x, got {version}"


@requires_mysql
def test_decimal_survives_the_round_trip():
    """Feasibility: does a DECIMAL column come back as Python Decimal?

    This is the single most important feasibility question in the
    project. If PyMySQL returned float here, the 20 lb threshold would be
    unreliable no matter how carefully the rule is written.
    """
    products = database.fetch_products()
    weight = products[0]["unit_weight_lb"]

    assert isinstance(weight, Decimal), (
        f"weights arrive as {type(weight).__name__}, not Decimal"
    )
    # And the value is exact, not a nearby float
    assert weight == Decimal("0.10")


@requires_mysql
def test_decimal_arithmetic_is_exact_after_reading_from_mysql():
    """Feasibility: ten lemons read from the database must weigh exactly
    1.00 lb. In float arithmetic this is 0.9999999999999999."""
    lemon = database.fetch_products_by_ids([LEMON_ID])[0]
    total = lemon["unit_weight_lb"] * 10
    assert total == Decimal("1.00")


@requires_mysql
def test_flask_serves_json_from_mysql(client):
    """Feasibility: Flask's routing, JSON encoding and the MySQL driver
    all work together in one request."""
    res = client.get("/api/products")
    assert res.status_code == 200

    body = res.get_json()
    assert body["ok"] is True
    assert body["weight_python_type"] == "Decimal"
    assert len(body["products"]) >= 3
    # Money and weight cross the wire as strings so precision is not lost
    assert body["products"][0]["unit_weight_lb"] == "0.10"


# =====================================================================
# B. USE CASE 1 — a customer chooses a product, and it is stored
# =====================================================================

@requires_mysql
def test_customer_choice_is_written_to_the_database(client, clean_cart):
    """Feasibility: can Flask write to MySQL and commit?

    The read-back uses a *different* connection, so a value still sitting
    in an uncommitted transaction would not appear.
    """
    customer_id = clean_cart

    res = client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": APPLE_ID, "quantity": 6,
    })
    assert res.status_code == 201
    assert res.get_json()["stored_in_database"] is True

    stored = database.fetch_cart(customer_id)
    assert len(stored) == 1
    assert stored[0]["product_id"] == APPLE_ID
    assert stored[0]["quantity"] == 6


@requires_mysql
def test_cart_persists_across_requests(client, clean_cart):
    """Feasibility: the cart lives in MySQL, not in Flask's memory. A
    second, separate request must see what the first one wrote."""
    customer_id = clean_cart

    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": WATER_ID, "quantity": 1,
    })

    res = client.get(f"/api/cart/{customer_id}")
    lines = res.get_json()["cart"]["lines"]
    assert len(lines) == 1
    assert lines[0]["product_id"] == WATER_ID


@requires_mysql
def test_choosing_the_same_product_twice_increases_quantity(client, clean_cart):
    """Feasibility: does ON DUPLICATE KEY UPDATE behave as expected,
    rather than raising a primary-key error?"""
    customer_id = clean_cart

    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": LEMON_ID, "quantity": 8})
    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": LEMON_ID, "quantity": 12})

    stored = database.fetch_cart(customer_id)
    assert len(stored) == 1, "should be one line, not two"
    assert stored[0]["quantity"] == 20


@requires_mysql
def test_stored_cart_produces_the_right_weight_and_charge(client, clean_cart):
    """Feasibility: the full chain end to end — values written to MySQL,
    read back, summed as Decimal, and run through the charge rule.

    6 apple bags (18.00) + 20 lemons (2.00) = exactly 20.00 lb, which
    must be charged.
    """
    customer_id = clean_cart

    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": APPLE_ID, "quantity": 6})
    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": LEMON_ID, "quantity": 20})

    cart = client.get(f"/api/cart/{customer_id}").get_json()["cart"]
    assert cart["total_weight_lb"] == "20.00"
    assert cart["delivery_fee"] == "10.00"
    assert cart["free_delivery"] is False


@requires_mysql
def test_removing_a_product_from_the_cart(client, clean_cart):
    customer_id = clean_cart
    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": WATER_ID, "quantity": 1})

    res = client.delete(f"/api/cart/{customer_id}/items/{WATER_ID}")
    assert res.status_code == 200
    assert database.fetch_cart(customer_id) == ()  or \
           len(database.fetch_cart(customer_id)) == 0


@requires_mysql
def test_database_rejects_a_product_that_does_not_exist(client, clean_cart):
    """Feasibility: is the foreign key actually enforced? InnoDB is
    required for this — a MyISAM table would silently accept it."""
    res = client.post("/api/cart/items", json={
        "customer_id": clean_cart, "product_id": 999999, "quantity": 1,
    })
    assert res.status_code == 409
    assert res.get_json()["ok"] is False


# =====================================================================
# C. USE CASE 2 — a store employee adds or removes a product
# =====================================================================

@requires_mysql
def test_employee_adds_a_product_and_it_appears_in_the_catalog(client):
    res = client.post("/api/admin/products", json={
        "name": "Organic Carrots, 2 lb bag",
        "price": "3.49",
        "unit_weight_lb": "2.00",
    })
    assert res.status_code == 201
    body = res.get_json()
    assert body["appears_in_catalog"] is True

    # Tidy up — unlist rather than delete, per USE CASE 2
    database.unlist_product(body["product_id"])


@requires_mysql
def test_database_refuses_a_product_without_a_valid_weight(client):
    """Feasibility: does MySQL enforce CHECK constraints?

    MySQL parsed but IGNORED CHECK constraints until version 8.0.16. If
    this test fails, the local MySQL is too old and the "weight is
    required" rule is not actually being enforced by the database.
    """
    res = client.post("/api/admin/products", json={
        "name": "Weightless Item", "price": "1.00", "unit_weight_lb": "0",
    })
    assert res.status_code == 409, (
        "MySQL accepted a zero weight — CHECK constraints are not being "
        "enforced. Check the server version is 8.0.16 or newer."
    )


@requires_mysql
def test_employee_removes_a_product_without_destroying_history(client, clean_cart, temp_product):
    """Feasibility: what does 'remove a product' mean when a customer
    already has it in their cart?

    A hard DELETE would fail on the foreign key from cart_items. The soft
    delete must hide the product from the catalog while leaving the row —
    and the customer's cart line — intact.
    """
    customer_id = clean_cart
    product_id = temp_product(name="Discontinued Item", weight="1.00")

    client.post("/api/cart/items", json={
        "customer_id": customer_id, "product_id": product_id, "quantity": 2})

    res = client.delete(f"/api/admin/products/{product_id}")
    assert res.status_code == 200
    body = res.get_json()

    assert body["still_in_catalog"] is False, "should disappear from the shop"
    assert body["row_still_exists"] is True, "row must survive for history"

    # The customer's existing cart line still resolves
    stored = database.fetch_cart(customer_id)
    assert any(line["product_id"] == product_id for line in stored)


@requires_mysql
def test_hard_delete_is_blocked_by_the_foreign_key(clean_cart, temp_product):
    """Feasibility, stated as a negative: prove the database will NOT let
    us delete a product a cart refers to. This is why unlist_product()
    exists instead of a DELETE."""
    import pymysql

    customer_id = clean_cart
    product_id = temp_product(name="Referenced Item", weight="1.00")
    database.add_to_cart(customer_id, product_id, 1)

    with database.get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM products WHERE product_id = %s",
                            (product_id,))
                conn.commit()
                raise AssertionError(
                    "MySQL allowed a product to be deleted while a cart "
                    "still referenced it — foreign keys are not enforced."
                )
            except pymysql.err.IntegrityError:
                conn.rollback()          # expected
