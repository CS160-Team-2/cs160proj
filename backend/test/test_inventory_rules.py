import pytest

from conftest import APPLES_ID, error_code, make_product, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

NEW = {"name": "Fresh Pears", "price": "3.25", "unit_weight_lb": "2.00", "category": "Fruits", "initial_stock": 5}


@pytest.mark.parametrize("price", ["0", "0.00", "0.004", 0])
def test_a_product_cannot_be_added_for_nothing(employee, price):
    response = employee.post("/api/admin/products", json={**NEW, "price": price})

    assert response.status_code == 400 and error_code(response) == "INVALID_PRICE"
    assert "more than zero" in response.get_json()["error"]["message"]


def test_a_price_cannot_be_edited_to_zero(employee):
    response = employee.patch(f"/api/admin/products/{APPLES_ID}", json={"price": "0"})

    assert response.status_code == 400 and error_code(response) == "INVALID_PRICE"
    assert employee.get(f"/api/admin/inventory?search=Apples").get_json()["inventory"][0]["price"] != "0.00"


def test_the_smallest_price_is_one_cent(employee):
    assert employee.post("/api/admin/products", json={**NEW, "price": "0.01"}).status_code == 201


def test_two_products_cannot_share_a_name(employee):
    assert employee.post("/api/admin/products", json=NEW).status_code == 201

    for name in ("Fresh Pears", "  fresh   PEARS ", "FRESH PEARS"):
        response = employee.post("/api/admin/products", json={**NEW, "name": name})
        assert response.status_code == 409 and error_code(response) == "DUPLICATE_PRODUCT_NAME"
    assert "already exists" in response.get_json()["error"]["message"]


def test_a_seeded_name_is_taken_too(employee):
    response = employee.post("/api/admin/products", json={**NEW, "name": "organic apples, 3 lb bag"})

    assert response.status_code == 409 and error_code(response) == "DUPLICATE_PRODUCT_NAME"


def test_a_product_can_be_renamed_to_a_new_name_and_keep_its_own_name(employee):
    assert employee.patch(f"/api/admin/products/{APPLES_ID}", json={"name": "Organic Apples, 3 lb bag", "price": "7.00"}).status_code == 200
    assert employee.patch(f"/api/admin/products/{APPLES_ID}", json={"name": "Crisp Apples"}).status_code == 200


def test_a_product_cannot_be_renamed_to_another_products_name(employee):
    response = employee.patch(f"/api/admin/products/{APPLES_ID}", json={"name": "Organic Bananas, bunch"})

    assert response.status_code == 409 and error_code(response) == "DUPLICATE_PRODUCT_NAME"


def test_an_unlisted_products_name_is_still_taken_and_the_message_says_to_list_it_again(employee):
    employee.delete(f"/api/admin/products/{APPLES_ID}")

    response = employee.post("/api/admin/products", json={**NEW, "name": "Organic Apples, 3 lb bag"})

    assert response.status_code == 409
    assert "unlisted" in response.get_json()["error"]["message"]


def test_the_staff_category_list_includes_categories_that_only_unlisted_products_have(employee, client):
    product_id = make_product(name="Last Mango", category="Tropical")
    employee.delete(f"/api/admin/products/{product_id}")

    assert "Tropical" not in client.get("/api/categories").get_json()["categories"]
    assert "Tropical" in employee.get("/api/admin/categories").get_json()["categories"]


def test_only_staff_can_read_the_staff_category_list(customer, client):
    assert customer.get("/api/admin/categories").status_code == 403
    assert client.get("/api/admin/categories").status_code == 401


def test_stock_history_is_newest_first_and_can_be_limited(employee):
    for amount in (1, 2, 3):
        employee.patch(f"/api/admin/inventory/{APPLES_ID}", json={"delta": amount, "reason": f"Delivery received {amount}"})

    everything = employee.get(f"/api/admin/inventory/{APPLES_ID}/changes").get_json()["changes"]
    two = employee.get(f"/api/admin/inventory/{APPLES_ID}/changes?limit=2").get_json()["changes"]

    assert [c["reason"] for c in everything[:3]] == ["Delivery received 3", "Delivery received 2", "Delivery received 1"]
    assert everything[0]["changed_by"] and everything[0]["created_at"]
    assert len(two) == 2 and two[0]["reason"] == "Delivery received 3"
    assert employee.get(f"/api/admin/inventory/{APPLES_ID}/changes?limit=abc").status_code == 400
    assert len(employee.get(f"/api/admin/inventory/{APPLES_ID}/changes?limit=0").get_json()["changes"]) == 1


@pytest.mark.parametrize("change", [
    {"price": "-1"}, {"price": "1e12"}, {"price": "abc"}, {"price": "NaN"}, {"price": "Infinity"},
    {"unit_weight_lb": "0"}, {"unit_weight_lb": "2000.01"}, {"unit_weight_lb": "abc"},
    {"name": "n" * 256}, {"name": "   "}, {"name": None}, {"name": 12},
    {"initial_stock": -1}, {"initial_stock": 1.5}, {"initial_stock": 2 ** 40}, {"initial_stock": "ten"}, {"initial_stock": True},
    {"low_stock_threshold": -1}, {"low_stock_threshold": 1.5},
    {"description": "d" * 70000}, {"category": "c" * 61}, {"category": ""},
])
def test_bad_values_on_the_add_form_are_refused_with_a_400(employee, change):
    response = employee.post("/api/admin/products", json={**NEW, **change})

    assert response.status_code == 400, response.get_data(as_text=True)


@pytest.mark.parametrize("change", [
    {"delta": 0, "reason": "x"}, {"delta": 1.5, "reason": "x"}, {"delta": "abc", "reason": "x"}, {"delta": 2 ** 31, "reason": "x"},
    {"delta": True, "reason": "x"}, {"delta": 1}, {"delta": 1, "reason": "   "}, {"delta": 1, "reason": "r" * 256},
    {"low_stock_threshold": -1}, {"low_stock_threshold": "a"}, {},
])
def test_bad_values_on_the_stock_change_are_refused_with_a_400(employee, change):
    assert employee.patch(f"/api/admin/inventory/{APPLES_ID}", json=change).status_code == 400


def test_odd_but_valid_text_is_kept_as_text(employee):
    for name in ("Pears 🍐 crème brûlée", "<script>alert(1)</script>", "O'Brien's \"best\" jam; DROP TABLE products;--"):
        response = employee.post("/api/admin/products", json={**NEW, "name": name})
        assert response.status_code == 201
        assert response.get_json()["product"]["name"] == name


def test_the_longest_allowed_name_and_the_smallest_weight_work(employee):
    assert employee.post("/api/admin/products", json={**NEW, "name": "n" * 160, "unit_weight_lb": "0.01"}).status_code == 201


def test_broken_json_and_unknown_filters_are_400s_not_crashes(employee):
    assert employee.patch("/api/admin/products/1", data="not json", content_type="application/json").status_code == 400
    assert employee.get("/api/admin/inventory?availability=bogus").status_code == 400
    assert employee.get("/api/admin/inventory?search=" + "a" * 500).status_code == 200
    assert employee.get("/api/admin/inventory/9999/changes").status_code == 404
    assert employee.delete("/api/admin/products/9999").status_code == 404
