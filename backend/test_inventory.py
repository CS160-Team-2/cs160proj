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
    import threading
    other = app.test_client()
    other.post("/api/auth/login", json={"email": "manager@ofs.test", "password": "manager-pass-1"})

    def adjust(client, delta):
        client.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": delta, "reason": "count"})

    threads = [threading.Thread(target=adjust, args=(employee, 5)),
               threading.Thread(target=adjust, args=(other, -2))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert stock_of(APPLES_ID) == 43


def test_initial_stock_is_logged(employee):
    product_id = employee.post("/api/admin/products", json=NEW_PRODUCT).get_json()["product"]["product_id"]
    log = database.query_one("SELECT changed_by, change_qty FROM inventory_log WHERE product_id = %s",
                             (product_id,))
    assert log == {"changed_by": EMPLOYEE_ID, "change_qty": 12}
