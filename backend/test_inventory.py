"""Catalog and inventory management for staff (API table VIII; backlog
B-06; test plan T-08)."""

import pytest

import db as database
from conftest import APPLES_ID, EMPLOYEE_ID, error_code, requires_mysql, stock_of

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

NEW_PRODUCT = {"name": "Organic Kale", "price": "3.49", "unit_weight_lb": "0.50",
               "category": "Vegetables", "initial_stock": 12}


def test_employee_adds_a_product_and_it_is_in_the_shop(client, employee):
    response = employee.post("/api/admin/products", json=NEW_PRODUCT)

    assert response.status_code == 201
    product_id = response.get_json()["product"]["product_id"]
    shop = client.get(f"/api/products/{product_id}").get_json()["product"]
    assert shop["available"] is True and shop["stock"] == 12


@pytest.mark.parametrize("change,code", [
    ({"unit_weight_lb": "0"}, "INVALID_WEIGHT"),
    ({"unit_weight_lb": "-2"}, "INVALID_WEIGHT"),
    ({"price": "-0.01"}, "INVALID_PRICE"),
    ({"price": "abc"}, "BAD_REQUEST"),
    ({"name": "  "}, "BAD_REQUEST"),
])
def test_product_validation(employee, change, code):
    response = employee.post("/api/admin/products", json={**NEW_PRODUCT, **change})
    assert response.status_code == 400
    assert error_code(response) == code


def test_editing_a_product(employee):
    response = employee.patch(f"/api/admin/products/{APPLES_ID}",
                              json={"price": "5.99", "description": "On sale"})
    product = response.get_json()["product"]
    assert product["price"] == "5.99" and product["description"] == "On sale"


def test_removing_a_product_unlists_it_but_keeps_the_row(client, employee):
    employee.delete(f"/api/admin/products/{APPLES_ID}")

    ids = [p["product_id"] for p in client.get("/api/products").get_json()["products"]]
    assert APPLES_ID not in ids
    assert database.query_one("SELECT is_listed FROM products WHERE product_id = %s",
                              (APPLES_ID,))["is_listed"] == 0

    employee.patch(f"/api/admin/products/{APPLES_ID}", json={"is_listed": True})
    ids = [p["product_id"] for p in client.get("/api/products").get_json()["products"]]
    assert APPLES_ID in ids


def test_stock_adjustment_is_logged_with_who_and_why(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                              json={"delta": -3, "reason": "Damaged in storage"})

    assert response.get_json()["product"]["stock"] == 37
    change = employee.get(f"/api/admin/inventory/{APPLES_ID}/changes").get_json()["changes"][0]
    assert change["change_qty"] == -3 and change["old_quantity"] == 40
    assert change["reason"] == "Damaged in storage" and change["changed_by"] == "Eli Park"


def test_stock_cannot_go_below_zero(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                              json={"delta": -41, "reason": "Oops"})
    assert error_code(response) == "NEGATIVE_STOCK"
    assert stock_of(APPLES_ID) == 40


def test_a_reason_is_required(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": 5})
    assert response.status_code == 400


def test_zero_stock_makes_a_product_unavailable_and_restocking_brings_it_back(client, employee):
    employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": -40, "reason": "Sold out"})
    assert client.get(f"/api/products/{APPLES_ID}").get_json()["product"]["available"] is False

    employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": 10, "reason": "Delivery"})
    assert client.get(f"/api/products/{APPLES_ID}").get_json()["product"]["available"] is True


def test_low_stock_uses_each_products_own_threshold(employee):
    employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"low_stock_threshold": 40})
    low = [p["product_id"] for p in employee.get("/api/admin/inventory/low-stock").get_json()["inventory"]]
    assert APPLES_ID in low

    employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": 1, "reason": "Found one"})
    low = [p["product_id"] for p in employee.get("/api/admin/inventory/low-stock").get_json()["inventory"]]
    assert APPLES_ID not in low


def test_inventory_search_and_filters(employee):
    employee.delete(f"/api/admin/products/{APPLES_ID}")
    unlisted = employee.get("/api/admin/inventory?availability=unlisted").get_json()["inventory"]
    assert [p["product_id"] for p in unlisted] == [APPLES_ID]

    found = employee.get("/api/admin/inventory?search=milk").get_json()["inventory"]
    assert found and all("milk" in p["name"].lower() for p in found)


def test_concurrent_adjustments_both_apply(app, employee):
    """Two employees adjusting at once: each delta lands, neither overwrites."""
    from concurrent.futures import ThreadPoolExecutor
    other = app.test_client()
    other.post("/api/auth/login", json={"email": "manager@ofs.test", "password": "manager-pass-1"})

    def adjust(client, delta):
        return client.patch(f"/api/admin/inventory/{APPLES_ID}",
                            json={"delta": delta, "reason": "count"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [pool.submit(adjust, employee, 5), pool.submit(adjust, other, -2)]
        assert [future.result(timeout=10).status_code for future in responses] == [200, 200]
    assert stock_of(APPLES_ID) == 43
    changes = database.query_all("SELECT old_quantity, new_quantity FROM inventory_log "
                                 "WHERE product_id = %s ORDER BY log_id", (APPLES_ID,))
    assert changes[0]["old_quantity"] == 40
    assert changes[0]["new_quantity"] == changes[1]["old_quantity"]
    assert changes[1]["new_quantity"] == 43


def test_initial_stock_is_logged(employee):
    product_id = employee.post("/api/admin/products", json=NEW_PRODUCT).get_json()["product"]["product_id"]
    log = database.query_one("SELECT changed_by, change_qty FROM inventory_log WHERE product_id = %s",
                             (product_id,))
    assert log == {"changed_by": EMPLOYEE_ID, "change_qty": 12}


INVENTORY_ENDPOINTS = [
    ("post", "/api/admin/products"),
    ("patch", f"/api/admin/products/{APPLES_ID}"),
    ("delete", f"/api/admin/products/{APPLES_ID}"),
    ("get", "/api/admin/inventory"),
    ("get", "/api/admin/inventory/low-stock"),
    ("patch", f"/api/admin/inventory/{APPLES_ID}"),
    ("get", f"/api/admin/inventory/{APPLES_ID}/changes"),
]


@pytest.mark.parametrize("method,path", INVENTORY_ENDPOINTS)
def test_inventory_rejects_signed_out_visitors(client, method, path):
    assert getattr(client, method)(path, json={}).status_code == 401


@pytest.mark.parametrize("method,path", INVENTORY_ENDPOINTS)
def test_inventory_rejects_customers(customer, method, path):
    assert getattr(customer, method)(path, json={}).status_code == 403


def test_manager_can_create_products(manager):
    assert manager.post("/api/admin/products", json=NEW_PRODUCT).status_code == 201


def test_zero_initial_stock_creates_inventory_without_a_stock_change(employee):
    response = employee.post("/api/admin/products", json={**NEW_PRODUCT, "initial_stock": 0})
    assert response.status_code == 201
    product_id = response.json["product"]["product_id"]
    assert response.json["product"]["stock"] == 0
    assert response.json["product"]["available"] is False
    assert stock_of(product_id) == 0
    assert not database.query_all("SELECT * FROM inventory_log WHERE product_id = %s", (product_id,))


def test_product_price_is_rounded_to_database_precision(employee):
    response = employee.post("/api/admin/products", json={**NEW_PRODUCT, "price": "1.001"})
    assert response.status_code == 201
    assert response.json["product"]["price"] == "1.00"


def test_product_accepts_numeric_limits(employee):
    response = employee.post("/api/admin/products", json={
        **NEW_PRODUCT, "price": "99999999.99", "unit_weight_lb": "2000.00",
        "initial_stock": 2147483647, "low_stock_threshold": 2147483647,
    })
    assert response.status_code == 201
    product = response.json["product"]
    assert product["price"] == "99999999.99"
    assert product["unit_weight_lb"] == "2000.00"
    assert product["stock"] == product["low_stock_threshold"] == 2147483647
    change = employee.get(f"/api/admin/inventory/{product['product_id']}/changes").json["changes"][0]
    assert change["new_quantity"] == change["change_qty"] == 2147483647


def test_small_weight_that_rounds_to_one_hundredth_is_accepted(employee):
    response = employee.post("/api/admin/products", json={**NEW_PRODUCT, "unit_weight_lb": "0.005"})
    assert response.status_code == 201
    assert response.json["product"]["unit_weight_lb"] == "0.01"


@pytest.mark.parametrize("payload,code", [
    ({"price": "100000000"}, "INVALID_PRICE"),
    ({"unit_weight_lb": "0.001"}, "INVALID_WEIGHT"),
])
def test_invalid_product_edit_preserves_saved_values(employee, payload, code):
    response = employee.patch(f"/api/admin/products/{APPLES_ID}", json=payload)
    assert response.status_code == 400
    assert error_code(response) == code
    product = employee.get("/api/admin/inventory?search=Organic Apples").json["inventory"][0]
    assert product["price"] == "6.49" and product["unit_weight_lb"] == "3.00"


@pytest.mark.parametrize("payload", [
    {"price": "100000000"}, {"price": "NaN"},
    {"unit_weight_lb": "0.001"}, {"unit_weight_lb": "2000.01"},
    {"unit_weight_lb": "Infinity"}, {"initial_stock": True},
    {"initial_stock": 1.5}, {"initial_stock": 2147483648},
    {"low_stock_threshold": 2147483648},
])
def test_product_input_limits_do_not_leave_partial_rows(employee, payload):
    """Unstorable input should be a client error, not a database-driven 500."""
    count = database.query_one("SELECT COUNT(*) AS count FROM products")["count"]
    assert employee.post("/api/admin/products", json={**NEW_PRODUCT, **payload}).status_code == 400
    assert database.query_one("SELECT COUNT(*) AS count FROM products")["count"] == count


@pytest.mark.parametrize("payload", [
    {"delta": 0, "reason": "No change"}, {"delta": True, "reason": "Bad"},
    {"delta": 1.5, "reason": "Bad"}, {"delta": 2147483648, "reason": "Bad"},
    {"delta": 1, "reason": " "}, {"low_stock_threshold": -1},
])
def test_invalid_stock_update_leaves_no_log(employee, payload):
    assert employee.patch(f"/api/admin/inventory/{APPLES_ID}", json=payload).status_code == 400
    assert stock_of(APPLES_ID) == 40
    assert not database.query_all("SELECT * FROM inventory_log")


def test_stock_overflow_is_rejected(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                              json={"delta": 2147483647, "reason": "Too much"})
    assert response.status_code in (400, 409)
    assert stock_of(APPLES_ID) == 40


def test_invalid_threshold_rolls_back_combined_stock_update(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                              json={"delta": 5, "reason": "Delivery", "low_stock_threshold": -1})
    assert response.status_code == 400
    assert stock_of(APPLES_ID) == 40
    assert not database.query_all("SELECT * FROM inventory_log")


def test_oversized_threshold_rolls_back_combined_stock_update(employee):
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                              json={"delta": 5, "reason": "Delivery", "low_stock_threshold": 2147483648})
    assert response.status_code == 400
    assert stock_of(APPLES_ID) == 40
    assert not database.query_all("SELECT * FROM inventory_log")
    assert database.query_one("SELECT low_stock_threshold FROM inventory WHERE product_id = %s",
                              (APPLES_ID,))["low_stock_threshold"] == 5


@pytest.mark.parametrize("operation", ["create", "stock"])
def test_audit_failure_rolls_back_the_inventory_mutation(employee, monkeypatch, operation):
    import pymysql

    before = database.query_one("SELECT COUNT(*) AS count FROM products")["count"]
    execute = pymysql.cursors.DictCursor.execute

    def fail_audit_insert(cursor, query, args=None):
        if query.lstrip().upper().startswith("INSERT INTO INVENTORY_LOG "):
            raise pymysql.err.OperationalError(1105, "Simulated audit write failure")
        return execute(cursor, query, args)

    monkeypatch.setattr(pymysql.cursors.DictCursor, "execute", fail_audit_insert)
    if operation == "create":
        response = employee.post("/api/admin/products", json=NEW_PRODUCT)
    else:
        response = employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                                  json={"delta": 5, "reason": "Delivery"})
    assert response.status_code == 500
    assert "Simulated" not in response.get_data(as_text=True)
    assert database.query_one("SELECT COUNT(*) AS count FROM products")["count"] == before
    product = database.query_one("SELECT price, is_listed FROM products WHERE product_id = %s", (APPLES_ID,))
    assert str(product["price"]) == "6.49" and product["is_listed"]
    assert stock_of(APPLES_ID) == 40
    assert database.query_one("SELECT low_stock_threshold FROM inventory WHERE product_id = %s",
                              (APPLES_ID,))["low_stock_threshold"] == 5
    assert not database.query_all("SELECT * FROM inventory_log")


def test_product_and_threshold_edits_do_not_create_stock_change_logs(employee):
    response = employee.patch(f"/api/admin/products/{APPLES_ID}", json={"price": "5.99"})
    assert response.status_code == 200
    assert response.json["product"]["price"] == "5.99"
    response = employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"low_stock_threshold": 8})
    assert response.status_code == 200
    assert response.json["product"]["low_stock_threshold"] == 8
    response = employee.delete(f"/api/admin/products/{APPLES_ID}")
    assert response.status_code == 200
    assert response.json["product"]["is_listed"] is False
    changes = employee.get(f"/api/admin/inventory/{APPLES_ID}/changes").json["changes"]
    assert changes == []
    assert stock_of(APPLES_ID) == 40


def test_unchanged_edits_and_repeated_unlisting_do_not_add_duplicate_logs(employee):
    employee.patch(f"/api/admin/products/{APPLES_ID}", json={"price": "6.49"})
    employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"low_stock_threshold": 5})
    employee.delete(f"/api/admin/products/{APPLES_ID}")
    employee.delete(f"/api/admin/products/{APPLES_ID}")
    assert not database.query_all("SELECT * FROM inventory_log")
    assert stock_of(APPLES_ID) == 40


def test_customer_id_in_request_cannot_forge_audit_actor(employee):
    employee.patch(f"/api/admin/inventory/{APPLES_ID}",
                   json={"delta": 1, "reason": "Count", "changed_by": 1})
    assert database.query_one("SELECT changed_by FROM inventory_log")["changed_by"] == EMPLOYEE_ID


def test_two_requests_cannot_remove_the_last_stock_twice(app, employee):
    from concurrent.futures import ThreadPoolExecutor
    from conftest import MANAGER, signed_in
    other = signed_in(app, *MANAGER)

    def remove(client):
        return client.patch(f"/api/admin/inventory/{APPLES_ID}",
                            json={"delta": -40, "reason": "Stock removal"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [pool.submit(remove, employee), pool.submit(remove, other)]
        assert sorted(future.result(timeout=10).status_code for future in responses) == [200, 409]
    assert stock_of(APPLES_ID) == 0
    assert len(database.query_all("SELECT * FROM inventory_log")) == 1
