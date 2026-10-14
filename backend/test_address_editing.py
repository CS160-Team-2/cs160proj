"""T-12: address-editing API responses and database effects."""

import pytest

import db as database
from conftest import (
    APPLES_ID, CUSTOMER_ADDRESS_ID, buy, error_code, requires_mysql,
)
from services import mapping

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

URL = f"/api/users/me/addresses/{CUSTOMER_ADDRESS_ID}"
NEW_ADDRESS = {
    "street": "200 E Santa Clara St",
    "city": "San Jose", "state": "CA", "zip_code": "95113",
}

def saved_address(address_id=CUSTOMER_ADDRESS_ID):
    return database.query_one(
        "SELECT * FROM addresses WHERE address_id = %s", (address_id,)
    )

def address_count():
    return database.query_one("SELECT COUNT(*) AS count FROM addresses")["count"]

def test_customer_edits_an_unused_address_in_place(customer):
    before = saved_address()
    count = address_count()
    response = customer.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 200
    result = response.get_json()["address"]
    after = saved_address()
    assert result["address_id"] == CUSTOMER_ADDRESS_ID
    assert address_count() == count
    for field, value in NEW_ADDRESS.items():
        assert result[field] == value
        assert after[field] == value
    assert after["user_id"] == before["user_id"]
    assert not after["is_deleted"]
    assert (after["latitude"], after["longitude"]) != (
        before["latitude"], before["longitude"]
    )
    assert mapping.provider().calls[-1] == (
        "geocode", NEW_ADDRESS["street"], NEW_ADDRESS["zip_code"]
    )


def test_partial_edit_keeps_unspecified_fields(customer):
    before = saved_address()
    response = customer.patch(URL, json={"street": "123 Main St"})
    assert response.status_code == 200
    result = response.get_json()["address"]
    after = saved_address()
    assert result["address_id"] == CUSTOMER_ADDRESS_ID
    assert after["street"] == result["street"] == "123 Main St"
    for field in ("city", "state", "zip_code"):
        assert after[field] == result[field] == before[field]

def test_edit_preserves_the_delivery_address_of_an_existing_order(customer):
    placed = buy(customer, {APPLES_ID: 1})
    assert placed.status_code == 201
    order = placed.get_json()["order"]
    original = order["address"]
    count = address_count()
    response = customer.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 200
    replacement = response.get_json()["address"]
    new_id = replacement["address_id"]
    assert new_id != CUSTOMER_ADDRESS_ID
    assert address_count() == count + 1
    assert saved_address()["is_deleted"]
    assert not saved_address(new_id)["is_deleted"]
    for field, value in NEW_ADDRESS.items():
        assert replacement[field] == saved_address(new_id)[field] == value
    old_order = database.query_one(
        "SELECT address_id FROM orders WHERE order_id = %s", (order["order_id"],)
    )
    assert old_order["address_id"] == CUSTOMER_ADDRESS_ID
    detail = customer.get(f"/api/orders/{order['order_number']}")
    assert detail.status_code == 200
    assert detail.get_json()["order"]["address"] == original
    addresses = customer.get("/api/users/me/addresses").get_json()["addresses"]
    ids = [item["address_id"] for item in addresses]
    assert new_id in ids
    assert CUSTOMER_ADDRESS_ID not in ids


def test_customer_cannot_edit_another_customers_address(client):
    before = saved_address()
    registered = client.post("/api/auth/register", json={
        "email": "address-rival@example.com",
        "password": "long-enough-1", "full_name": "Other Customer",
    })
    assert registered.status_code == 201
    response = client.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 404
    assert error_code(response) == "NOT_FOUND"
    assert saved_address() == before


@pytest.mark.parametrize("changes,code", [
    ({"zip_code": "abcde"}, "INVALID_ZIP"),
    ({"street": " "}, "BAD_REQUEST"),
])
def test_invalid_edit_preserves_the_original_address(customer, changes, code):
    before = saved_address()
    count = address_count()
    response = customer.patch(URL, json=changes)
    assert response.status_code == 400
    assert error_code(response) == code
    assert saved_address() == before
    assert address_count() == count


def test_unfindable_edit_preserves_the_original_address(customer):
    before = saved_address()
    count = address_count()
    response = customer.patch(URL, json={"street": "1 Nowhere Lane"})
    assert response.status_code == 422
    assert error_code(response) == "ADDRESS_NOT_FOUND"
    assert saved_address() == before
    assert address_count() == count


def test_mapping_outage_does_not_save_the_edit(customer):
    class UnavailableMap(mapping.FakeMapProvider):
        def geocode(self, street, city, state, zip_code):
            raise mapping.MappingError("Simulated mapping outage")

    mapping.use_provider(UnavailableMap())
    before = saved_address()
    count = address_count()
    response = customer.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 503
    assert error_code(response) == "MAPPING_UNAVAILABLE"
    assert saved_address() == before
    assert address_count() == count


def test_deleted_address_cannot_be_edited(customer):
    deleted = customer.delete(URL)
    assert deleted.status_code == 200
    before = saved_address()
    response = customer.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 404
    assert error_code(response) == "NOT_FOUND"
    assert saved_address() == before


def test_signed_out_visitor_cannot_edit_addresses(client):
    before = saved_address()
    response = client.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"
    assert saved_address() == before


@pytest.mark.parametrize("role_fixture", ["employee", "manager"])
def test_staff_cannot_edit_customer_addresses(request, role_fixture):
    staff = request.getfixturevalue(role_fixture)
    before = saved_address()
    response = staff.patch(URL, json=NEW_ADDRESS)
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"
    assert saved_address() == before