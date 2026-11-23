import pytest

from conftest import buy, make_product, ready_order, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

SUMMARY_KEYS = {"order_id", "order_number", "status", "placed_at", "delivered_at", "total_weight_lb",
                "grand_total", "customer_name", "item_count", "trip_id", "unscheduled_reason"}
DETAIL_KEYS = {"order_id", "order_number", "status", "placed_at", "delivered_at", "subtotal", "tax", "delivery_fee",
               "total_weight_lb", "grand_total", "customer_name", "items", "history", "trip", "unscheduled_reason"}


# Places one order that stays at "placed" and returns its order id.
def placed_order(customer):
    product_id = make_product(weight="1.00", stock=10)
    placed = buy(customer, {product_id: 2})
    assert placed.status_code == 201, placed.get_json()
    return placed.get_json()["order"]["order_id"]


def test_an_employee_sees_every_order_with_only_safe_fields(customer, manager, employee):
    placed_order(customer)
    ready_order(customer, manager)

    response = employee.get("/api/staff/orders")

    assert response.status_code == 200
    orders = response.get_json()["orders"]
    assert len(orders) == 2
    assert all(set(order) == SUMMARY_KEYS for order in orders)
    assert {order["status"] for order in orders} == {"placed", "awaiting_delivery"}
    assert all(order["customer_name"] == "Anna Rivera" and order["item_count"] >= 1 for order in orders)
    text = response.get_data(as_text=True).lower()
    assert "customer@ofs.test" not in text and "street" not in text and "card_last4" not in text


def test_the_list_can_be_filtered_by_status_and_counted(customer, manager, employee):
    placed_order(customer)
    ready_order(customer, manager)

    waiting = employee.get("/api/staff/orders?status=awaiting_delivery&page=1&per_page=10").get_json()

    assert [o["status"] for o in waiting["orders"]] == ["awaiting_delivery"]
    assert waiting["status_counts"]["placed"] == 1 and waiting["status_counts"]["awaiting_delivery"] == 1
    assert waiting["pagination"]["total"] == 1


def test_the_list_is_paged(customer, employee):
    for _ in range(3):
        placed_order(customer)

    first = employee.get("/api/staff/orders?page=1&per_page=2").get_json()
    second = employee.get("/api/staff/orders?page=2&per_page=2").get_json()

    assert len(first["orders"]) == 2 and len(second["orders"]) == 1
    assert first["pagination"]["total"] == 3


def test_search_finds_an_order_number_or_a_name_but_never_an_email(customer, manager, employee):
    placed_order(customer)
    number = employee.get("/api/staff/orders").get_json()["orders"][0]["order_number"]

    assert len(employee.get(f"/api/staff/orders?q={number}").get_json()["orders"]) == 1
    assert len(employee.get("/api/staff/orders?q=Rivera").get_json()["orders"]) == 1
    assert employee.get("/api/staff/orders?q=customer@ofs.test").get_json()["orders"] == []
    assert len(manager.get("/api/admin/orders?q=customer@ofs.test").get_json()["orders"]) == 1
    assert employee.get("/api/staff/orders?q=nobody-by-this-name").get_json()["orders"] == []


def test_bad_filters_are_refused_like_the_managers_list(employee):
    assert employee.get("/api/staff/orders?status=shipped").status_code == 400
    assert employee.get("/api/staff/orders?from=yesterday").status_code == 400


def test_the_detail_shows_items_totals_and_progress_but_no_contact_or_payment(customer, manager, employee):
    order_id = ready_order(customer, manager)

    response = employee.get(f"/api/staff/orders/{order_id}")

    assert response.status_code == 200
    order = response.get_json()["order"]
    assert set(order) == DETAIL_KEYS
    assert order["items"][0]["quantity"] == 1 and order["items"][0]["name"]
    assert [h["status"] for h in order["history"]] == ["placed", "awaiting_delivery"]
    assert order["trip"] is None
    text = response.get_data(as_text=True).lower()
    assert "customer@ofs.test" not in text and "address" not in text and "payment" not in text and "card" not in text


def test_the_detail_of_an_order_on_a_trip_names_the_trip(customer, manager, employee):
    order_id = ready_order(customer, manager)
    trip = manager.post("/api/admin/delivery/trips", json={"order_ids": [order_id]}).get_json()["trip"]

    order = employee.get(f"/api/staff/orders/{order_id}").get_json()["order"]

    assert order["status"] == "assigned_to_trip" and order["trip"]["trip_id"] == trip["trip_id"]


def test_an_unknown_order_is_a_404(employee):
    assert employee.get("/api/staff/orders/99999").status_code == 404


def test_managers_can_use_the_staff_view_too(customer, manager):
    placed_order(customer)

    assert len(manager.get("/api/staff/orders").get_json()["orders"]) == 1


def test_customers_and_visitors_cannot_use_it(customer, client):
    order_id = placed_order(customer)

    assert customer.get("/api/staff/orders").status_code == 403
    assert customer.get(f"/api/staff/orders/{order_id}").status_code == 403
    assert client.get("/api/staff/orders").status_code == 401


def test_an_employee_still_cannot_change_an_order_or_use_the_manager_list(customer, employee):
    order_id = placed_order(customer)

    assert employee.get("/api/admin/orders").status_code == 403
    assert employee.patch(f"/api/admin/orders/{order_id}/status", json={"status": "awaiting_delivery"}).status_code == 403
    assert employee.patch(f"/api/staff/orders/{order_id}", json={"status": "delivered"}).status_code == 405
    assert employee.post(f"/api/staff/orders/{order_id}").status_code == 405
