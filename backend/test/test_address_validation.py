import pytest

import db as database
from conftest import APPLES_ID, CUSTOMER_ADDRESS_ID, error_code, requires_mysql
from services import mapping

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

FAKE = {"street": "123 Fake Dr", "city": "San Jose", "state": "CA", "zip_code": "95192"}
REAL = {"street": "1 Washington Sq", "city": "San Jose", "state": "CA", "zip_code": "95192"}
CONTACT = {"first_name": "Anna", "last_name": "Tester", "email": "anna@example.com", "phone": "408-555-0123"}

GUESS = {"features": [{
    "center": [-121.8, 37.3], "relevance": 0.67, "text": "Faye Park Drive",
    "properties": {"accuracy": "street"},
    "context": [{"id": "postcode.1", "text": "95136"}, {"id": "place.1", "text": "San Jose"},
                {"id": "region.1", "text": "California", "short_code": "US-CA"}]}]}
FOUND = {"features": [{
    "center": [-121.88, 37.33], "relevance": 0.9, "address": "1", "text": "Washington Square",
    "properties": {"accuracy": "rooftop"},
    "context": [{"id": "postcode.1", "text": "95112"}, {"id": "place.1", "text": "San Jose"},
                {"id": "region.1", "text": "California", "short_code": "US-CA"}]}]}


# Makes the mapping service answer like Mapbox: a guess for fake addresses, the match for real ones.
@pytest.fixture
def mapbox(monkeypatch):
    mapping.use_provider(mapping.MapboxProvider("test-token"))
    monkeypatch.setattr(mapping, "_get_json", lambda url: FOUND if "Washington" in url else GUESS)


# How many addresses are saved.
def address_count():
    return database.query_one("SELECT COUNT(*) AS n FROM addresses")["n"]


def test_a_signed_in_customer_cannot_save_a_made_up_address(customer, mapbox):
    before = address_count()

    response = customer.post("/api/users/me/addresses", json=FAKE)

    assert response.status_code == 422 and error_code(response) == "ADDRESS_NOT_FOUND"
    assert address_count() == before


def test_a_real_address_is_still_saved_with_its_coordinates(customer, mapbox):
    response = customer.post("/api/users/me/addresses", json=REAL)

    assert response.status_code == 201
    assert str(response.get_json()["address"]["latitude"]) == "37.330000"


def test_editing_an_address_into_a_made_up_one_is_refused_and_keeps_the_old_one(customer, mapbox):
    before = database.query_one("SELECT street FROM addresses WHERE address_id = %s", (CUSTOMER_ADDRESS_ID,))

    response = customer.patch(f"/api/users/me/addresses/{CUSTOMER_ADDRESS_ID}", json=FAKE)

    assert response.status_code == 422 and error_code(response) == "ADDRESS_NOT_FOUND"
    after = database.query_one("SELECT street FROM addresses WHERE address_id = %s", (CUSTOMER_ADDRESS_ID,))
    assert after == before


def test_guest_checkout_with_a_made_up_address_creates_nothing(client, mapbox):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    users, addresses = database.query_one("SELECT COUNT(*) AS n FROM users")["n"], address_count()

    response = client.post("/api/checkout/guest", json={"contact": CONTACT, "address": FAKE})

    assert response.status_code == 422 and error_code(response) == "ADDRESS_NOT_FOUND"
    assert database.query_one("SELECT COUNT(*) AS n FROM users")["n"] == users
    assert address_count() == addresses


def test_guest_checkout_with_a_real_address_still_works(client, mapbox):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})

    response = client.post("/api/checkout/guest", json={"contact": CONTACT, "address": REAL})

    assert response.status_code == 201


OAKLAND = {"street": "1 Frank H Ogawa Plz", "city": "Oakland", "state": "CA", "zip_code": "94612"}
FREMONT = {"street": "39300 Civic Center Dr", "city": "Fremont", "state": "CA", "zip_code": "94538"}


# A map service that finds every address, at the coordinates it is given by city.
class CityMap(mapping.FakeMapProvider):
    PLACES = {"Oakland": ("37.8044", "-122.2712"), "Fremont": ("37.5483", "-121.9886"), "San Jose": ("37.3352", "-121.8811")}

    def geocode(self, street, city, state, zip_code):
        from decimal import Decimal
        lat, lng = self.PLACES[city]
        return mapping.GeoPoint(Decimal(lat), Decimal(lng))


@pytest.fixture
def city_map():
    mapping.use_provider(CityMap())


@pytest.mark.parametrize("miles, inside", [(0, True), (12.7, True), (24.99, True), (25, True), (25.01, False), (25.8, False), (42.5, False)])
def test_the_delivery_radius_rule(miles, inside):
    import rules
    assert rules.is_in_service_area(miles) is inside


def test_distance_from_the_store_is_straight_line_miles(city_map):
    assert 38 < mapping.miles_from_store(CityMap().geocode("x", "Oakland", "CA", "94612")) < 40
    assert 15 < mapping.miles_from_store(CityMap().geocode("x", "Fremont", "CA", "94538")) < 17
    assert mapping.miles_from_store(mapping.store_location()) == 0


def test_an_address_outside_the_delivery_area_cannot_be_saved(customer, city_map):
    before = address_count()

    response = customer.post("/api/users/me/addresses", json=OAKLAND)

    assert response.status_code == 422 and error_code(response) == "OUTSIDE_DELIVERY_AREA"
    message = response.get_json()["error"]["message"]
    assert "within 25 miles" in message and "39 miles away" in message
    assert address_count() == before


def test_an_address_inside_the_area_but_not_in_san_jose_is_saved(customer, city_map):
    assert customer.post("/api/users/me/addresses", json=FREMONT).status_code == 201


def test_editing_an_address_to_one_outside_the_area_is_refused(customer, city_map):
    response = customer.patch(f"/api/users/me/addresses/{CUSTOMER_ADDRESS_ID}", json=OAKLAND)

    assert response.status_code == 422 and error_code(response) == "OUTSIDE_DELIVERY_AREA"


def test_guest_checkout_outside_the_area_creates_nothing(client, city_map):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    users = database.query_one("SELECT COUNT(*) AS n FROM users")["n"]

    response = client.post("/api/checkout/guest", json={"contact": CONTACT, "address": OAKLAND})

    assert response.status_code == 422 and error_code(response) == "OUTSIDE_DELIVERY_AREA"
    assert database.query_one("SELECT COUNT(*) AS n FROM users")["n"] == users


def test_a_made_up_address_is_still_reported_as_not_found_not_as_outside(customer, mapbox):
    assert error_code(customer.post("/api/users/me/addresses", json=FAKE)) == "ADDRESS_NOT_FOUND"
