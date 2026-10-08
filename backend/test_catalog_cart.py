"""Catalog, addresses and cart (API tables III, IV and V; backlog B-05,
B-07, B-08)."""

from decimal import Decimal

import pytest

import db as database
from conftest import (APPLES_ID, CUSTOMER, error_code, make_product, requires_mysql,
                      signed_in)

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


# --- Catalog ----------------------------------------------------------

def test_catalog_lists_seeded_products_with_live_stock(client):
    products = client.get("/api/products").get_json()["products"]
    apples = next(p for p in products if p["product_id"] == APPLES_ID)

    assert len(products) == 39
    assert apples["price"] == "6.49"            # strings, not floats
    assert apples["unit_weight_lb"] == "3.00"
    assert apples["stock"] == 40 and apples["available"] is True


def test_search_filter_and_sort(client):
    found = client.get("/api/products?search=apple").get_json()["products"]
    assert found and all("apple" in p["name"].lower() for p in found)

    fruits = client.get("/api/products?category=Fruits").get_json()["products"]
    assert fruits and all(p["category"] == "Fruits" for p in fruits)

    cheap = client.get("/api/products?max_price=3&sort=price_desc").get_json()["products"]
    prices = [Decimal(p["price"]) for p in cheap]
    assert prices == sorted(prices, reverse=True) and max(prices) <= 3


def test_bad_sort_is_rejected(client):
    assert client.get("/api/products?sort=random").status_code == 400


def test_categories(client):
    categories = client.get("/api/categories").get_json()["categories"]
    assert "Fruits" in categories and "Vegetables" in categories


def test_out_of_stock_products_are_shown_as_unavailable(client):
    product_id = make_product(stock=0)
    product = client.get(f"/api/products/{product_id}").get_json()["product"]
    assert product["available"] is False


def test_unknown_product_is_404(client):
    assert client.get("/api/products/99999").status_code == 404


# --- Addresses --------------------------------------------------------

ADDRESS = {"street": "200 E Santa Clara St", "city": "San Jose", "state": "CA",
           "zip_code": "95113"}


def test_saving_an_address_geocodes_it(customer):
    response = customer.post("/api/users/me/addresses", json=ADDRESS)

    assert response.status_code == 201
    address = response.get_json()["address"]
    assert address["latitude"] and address["longitude"]
    assert len(customer.get("/api/users/me/addresses").get_json()["addresses"]) == 2


def test_an_address_the_map_cannot_find_is_not_saved(customer):
    response = customer.post("/api/users/me/addresses",
                             json={**ADDRESS, "street": "1 Nowhere Lane"})

    assert response.status_code == 422
    assert error_code(response) == "ADDRESS_NOT_FOUND"
    assert len(customer.get("/api/users/me/addresses").get_json()["addresses"]) == 1


def test_deleting_an_address_hides_it_but_keeps_the_row(customer):
    address_id = customer.post("/api/users/me/addresses", json=ADDRESS).get_json()["address"]["address_id"]
    customer.delete(f"/api/users/me/addresses/{address_id}")

    ids = [a["address_id"] for a in customer.get("/api/users/me/addresses").get_json()["addresses"]]
    assert address_id not in ids
    assert database.query_one("SELECT is_deleted FROM addresses WHERE address_id = %s",
                              (address_id,))["is_deleted"]


def test_customers_cannot_touch_each_others_addresses(app, client):
    client.post("/api/auth/register", json={
        "email": "other@example.com", "password": "long-enough-1", "full_name": "Other"})
    assert client.delete("/api/users/me/addresses/1").status_code == 404


# --- Cart -------------------------------------------------------------

def add(client, product_id, quantity):
    return client.post("/api/cart/items", json={"product_id": product_id, "quantity": quantity})


def test_adding_the_same_product_twice_increases_the_quantity(customer):
    add(customer, APPLES_ID, 2)
    cart = add(customer, APPLES_ID, 3).get_json()["cart"]

    assert cart["items"][0]["quantity"] == 5
    assert cart["total_weight_lb"] == "15.00"


def test_cart_is_saved_in_the_database(app, customer):
    add(customer, APPLES_ID, 2)
    same_customer_elsewhere = signed_in(app, *CUSTOMER)
    assert same_customer_elsewhere.get("/api/cart").get_json()["cart"]["item_count"] == 2


@pytest.mark.parametrize("weight,quantity,fee", [
    ("19.99", 1, "0.00"),
    ("20.00", 1, "10.00"),        # exactly 20 lb is charged
    ("2.00", 10, "10.00"),        # reaching 20 lb through quantity
    ("0.10", 199, "0.00"),        # 19.90 lb, no float drift
])
def test_delivery_fee_in_the_cart(customer, weight, quantity, fee):
    product_id = make_product(weight=weight, stock=500)
    cart = add(customer, product_id, quantity).get_json()["cart"]
    assert cart["delivery_fee"] == fee


def test_cannot_add_more_than_is_in_stock(customer):
    product_id = make_product(stock=3)
    add(customer, product_id, 2)
    response = add(customer, product_id, 2)

    assert response.status_code == 409
    assert error_code(response) == "NOT_ENOUGH_STOCK"


@pytest.mark.parametrize("quantity", [0, -1, "two", 1.5, True])
def test_quantity_must_be_a_positive_whole_number(customer, quantity):
    assert add(customer, APPLES_ID, quantity).status_code == 400


def test_unlisted_products_cannot_be_added(customer, employee):
    employee.delete(f"/api/admin/products/{APPLES_ID}")
    assert error_code(add(customer, APPLES_ID, 1)) == "PRODUCT_UNAVAILABLE"


def test_set_quantity_and_remove(customer):
    add(customer, APPLES_ID, 1)
    assert customer.patch(f"/api/cart/items/{APPLES_ID}",
                          json={"quantity": 4}).get_json()["cart"]["item_count"] == 4
    assert customer.delete(f"/api/cart/items/{APPLES_ID}").get_json()["cart"]["items"] == []
    assert customer.delete(f"/api/cart/items/{APPLES_ID}").status_code == 404


def test_cart_flags_items_whose_stock_dropped(customer):
    product_id = make_product(stock=5)
    add(customer, product_id, 5)
    with database.transaction() as cur:
        cur.execute("UPDATE inventory SET quantity_in_stock = 2 WHERE product_id = %s",
                    (product_id,))

    cart = customer.get("/api/cart").get_json()["cart"]
    assert cart["items"][0]["problem"] == "Only 2 left in stock"
    assert cart["can_check_out"] is False


def test_visitors_can_fill_a_cart_and_keep_it_when_they_sign_in(client):
    add(client, APPLES_ID, 2)
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 2

    client.post("/api/auth/login", json={"email": CUSTOMER[0], "password": CUSTOMER[1]})
    assert client.get("/api/cart").get_json()["cart"]["item_count"] == 2
    saved = database.query_one(
        "SELECT ci.quantity FROM cart_items ci JOIN carts c ON c.cart_id = ci.cart_id "
        "WHERE c.user_id = 1")
    assert saved["quantity"] == 2


def test_staff_do_not_have_carts(employee):
    assert employee.get("/api/cart").status_code == 403
