from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from services import mapping


def test_fake_geocoding_is_repeatable_and_rejects_unknown_addresses():
    provider = mapping.FakeMapProvider()
    first = provider.geocode("200 E Santa Clara St", "San Jose", "CA", "95113")
    second = provider.geocode("200 E Santa Clara St", "San Jose", "CA", "95113")

    assert first == second
    assert first.latitude.as_tuple().exponent == -6
    assert first.longitude.as_tuple().exponent == -6
    assert provider.geocode("1 Nowhere Lane", "San Jose", "CA", "95113") is None


def test_fake_route_visits_every_stop_and_returns_to_the_store():
    provider = mapping.FakeMapProvider()
    store = mapping.GeoPoint(Decimal("37.335200"), Decimal("-121.881100"))
    stops = [
        (10, mapping.GeoPoint(Decimal("37.340000"), Decimal("-121.880000"))),
        (20, mapping.GeoPoint(Decimal("37.350000"), Decimal("-121.900000"))),
    ]

    route = provider.route(store, stops)

    assert sorted(route.stop_order) == [10, 20]
    assert set(route.arrival_seconds) == {10, 20}
    assert route.arrival_seconds[route.stop_order[0]] < route.arrival_seconds[route.stop_order[1]]
    assert route.path[0] == route.path[-1] == [37.3352, -121.8811]
    assert route.provider == "fake"


def test_google_geocoding_builds_the_request_and_reads_coordinates(monkeypatch):
    requested = []

    def response(url):
        requested.append(url)
        return {
            "status": "OK",
            "results": [{"geometry": {"location_type": "ROOFTOP", "location": {
                "lat": 37.3371234,
                "lng": -121.8879876,
            }}, "address_components": [
                {"types": ["street_number"], "long_name": "200", "short_name": "200"},
                {"types": ["route"], "long_name": "East Santa Clara Street", "short_name": "E Santa Clara St"},
                {"types": ["locality"], "long_name": "San Jose", "short_name": "San Jose"},
                {"types": ["administrative_area_level_1"], "long_name": "California", "short_name": "CA"},
                {"types": ["postal_code"], "long_name": "95113", "short_name": "95113"},
            ]}],
        }

    monkeypatch.setattr(mapping, "_get_json", response)
    provider = mapping.GoogleMapProvider("test-key")
    result = provider.geocode("200 E Santa Clara St", "San Jose", "CA", "95113")

    assert result == mapping.GeoPoint(Decimal("37.337123"), Decimal("-121.887988"))
    query = parse_qs(urlparse(requested[0]).query)
    assert query["address"] == ["200 E Santa Clara St, San Jose, CA 95113"]
    assert query["components"] == ["country:US"]
    assert query["key"] == ["test-key"]


def test_google_geocoding_handles_no_result_and_provider_error(monkeypatch):
    provider = mapping.GoogleMapProvider("test-key")
    monkeypatch.setattr(mapping, "_get_json", lambda _url: {"status": "ZERO_RESULTS"})
    assert provider.geocode("1 Nowhere", "San Jose", "CA", "95113") is None

    monkeypatch.setattr(
        mapping, "_get_json", lambda _url: {"status": "REQUEST_DENIED"})
    with pytest.raises(mapping.MappingError, match="REQUEST_DENIED"):
        provider.geocode("200 E Santa Clara St", "San Jose", "CA", "95113")


def test_google_routes_uses_traffic_and_optimized_waypoint_order(monkeypatch):
    captured = {}

    def response(url, *, payload=None, headers=None):
        captured.update(url=url, payload=payload, headers=headers)
        return {"routes": [{
            "optimizedIntermediateWaypointIndex": [1, 0],
            "legs": [
                {"duration": "100s"},
                {"duration": "200.4s"},
                {"duration": "300s"},
            ],
            "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        }]}

    monkeypatch.setattr(mapping, "_request_json", response)
    provider = mapping.GoogleMapProvider("test-key")
    store = mapping.GeoPoint(Decimal("37.3352"), Decimal("-121.8811"))
    stops = [
        (10, mapping.GeoPoint(Decimal("37.34"), Decimal("-121.89"))),
        (20, mapping.GeoPoint(Decimal("37.35"), Decimal("-121.90"))),
    ]

    route = provider.route(store, stops)

    assert captured["url"] == mapping.GoogleMapProvider.ROUTES_URL
    assert captured["headers"]["X-Goog-Api-Key"] == "test-key"
    assert "optimizedIntermediateWaypointIndex" in captured["headers"]["X-Goog-FieldMask"]
    assert captured["payload"]["routingPreference"] == "TRAFFIC_AWARE"
    assert captured["payload"]["optimizeWaypointOrder"] is True
    assert route.stop_order == [20, 10]
    assert route.arrival_seconds == {20: 100, 10: 480}
    assert route.total_seconds == 960
    assert route.path == [
        [38.5, -120.2],
        [40.7, -120.95],
        [43.252, -126.453],
    ]
    assert route.provider == "google"


@pytest.mark.parametrize("response,message", [
    ({"error": {"message": "API key is invalid"}}, "API key is invalid"),
    ({"routes": [{"optimizedIntermediateWaypointIndex": [0, 0], "legs": []}]},
     "invalid waypoint order"),
])
def test_google_routes_rejects_unusable_responses(monkeypatch, response, message):
    monkeypatch.setattr(
        mapping, "_request_json", lambda _url, **_kwargs: response)
    provider = mapping.GoogleMapProvider("test-key")
    store = mapping.GeoPoint(Decimal("37.3352"), Decimal("-121.8811"))
    stops = [
        (10, mapping.GeoPoint(Decimal("37.34"), Decimal("-121.89"))),
        (20, mapping.GeoPoint(Decimal("37.35"), Decimal("-121.90"))),
    ]

    with pytest.raises(mapping.MappingError, match=message):
        provider.route(store, stops)


def test_google_maps_directions_link_needs_no_key():
    origin = mapping.GeoPoint(Decimal("37.335200"), Decimal("-121.881100"))
    destination = mapping.GeoPoint(Decimal("37.340000"), Decimal("-121.890000"))

    url = mapping.directions_url(origin, destination)
    query = parse_qs(urlparse(url).query)

    assert url.startswith("https://www.google.com/maps/dir/")
    assert query == {
        "api": ["1"],
        "origin": ["37.335200,-121.881100"],
        "destination": ["37.340000,-121.890000"],
        "travelmode": ["driving"],
    }
    assert "key" not in query


# What Mapbox answers with
def mapbox_answer(address, street, relevance=1, accuracy="rooftop", place="San Jose", region=("California", "US-CA"), postcode="95192"):
    return {"features": [{
        "center": [-121.88, 37.33], "relevance": relevance, "address": address, "text": street,
        "properties": {"accuracy": accuracy},
        "context": [{"id": "postcode.1", "text": postcode}, {"id": "place.1", "text": place},
                    {"id": "region.1", "text": region[0], "short_code": region[1]}],
    }]}


# Asks the Mapbox adapter about an address while the service answers with the given guess.
def ask_mapbox(monkeypatch, answer, street="123 Fake Dr", city="San Jose", state="CA", zip_code="95192"):
    monkeypatch.setattr(mapping, "_get_json", lambda _url: answer)
    return mapping.MapboxProvider("test-token").geocode(street, city, state, zip_code)


@pytest.mark.parametrize("typed, found, expected", [
    (("1 Washington Sq", "San Jose", "CA", "95192"), ("1", "Washington Square", "San Jose", ("CA", "California"), "95112"), True),
    (("350 5th Ave", "New York", "NY", "10118"), ("350", "Fifth Avenue", "New York", ("NY", "New York"), "10118"), True),
    (("200 East Santa Clara Street, Apt 4B", "San Jose", "California", "95113"), ("200", "East Santa Clara Street", "San Jose", ("CA", "California"), "95113"), True),
    (("200 E Santa Clara St", "San Jose", "CA", "95113"), ("200", "East Santa Clara Street", "San Jose", ("CA", "California"), "95113"), True),
    (("12 Saint James Pl", "San Jose", "CA", "95112"), ("12", "St James Place", "San Jose", ("CA", "California"), "95112"), True),
    (("1 Washingtn Sq", "San Jose", "CA", "95192"), ("1", "Washington Square", "San Jose", ("CA", "California"), "95192"), True),
    (("123 Fake Dr", "San Jose", "CA", "95192"), ("123", "Faye Park Drive", "San Jose", ("CA", "California"), "95136"), False),
    (("123 Fake Dr", "San Jose", "CA", "95192"), ("123", "Lake Drive", "Orleans", ("MA", "Massachusetts"), "02653"), False),
    (("123 Fake Dr", "San Jose", "CA", "95192"), ("1", "Fake Drive", "San Jose", ("CA", "California"), "95192"), False),
    (("1 Washington Sq", "Los Angeles", "CA", "90001"), ("1", "Washington Boulevard", "Marina del Rey", ("CA", "California"), "90292"), False),
    (("1 Washington Sq", "San Jose", "CA", "95192"), ("1", "Washington Street", "San Jose", ("CA", "California"), "95192"), False),
    (("1 Washington Sq", "San Jose", "CA", "95192"), ("1", "Washington Square", "Reno", ("NV", "Nevada"), "89501"), False),
    (("Main Street", "San Jose", "CA", "95192"), ("1", "Main Street", "San Jose", ("CA", "California"), "95192"), False),
])
def test_a_found_address_is_accepted_only_when_it_matches_what_was_typed(typed, found, expected):
    number, street, city, region, postcode = found

    assert mapping.address_matches(*typed, number, street, city, region, postcode) is expected


def test_mapbox_refuses_a_guessed_street_for_a_fake_address(monkeypatch):
    guess = mapbox_answer(None, "Faye Park Drive", relevance=0.67, accuracy="street", postcode="95136")

    assert ask_mapbox(monkeypatch, guess) is None


def test_mapbox_refuses_a_guess_in_another_state_and_a_weak_match(monkeypatch):
    assert ask_mapbox(monkeypatch, mapbox_answer("123", "Lake Drive", relevance=0.39, place="Orleans",
                                                 region=("Massachusetts", "US-MA"), postcode="02653")) is None
    assert ask_mapbox(monkeypatch, mapbox_answer("123", "Fake Drive", relevance=0.4)) is None


def test_mapbox_accepts_the_real_address_in_other_words(monkeypatch):
    found = ask_mapbox(monkeypatch, mapbox_answer("1", "Washington Square", postcode="95112"),
                       street="1 Washington Sq", zip_code="95192")

    assert found == mapping.GeoPoint(Decimal("37.330000"), Decimal("-121.880000"))


def test_google_refuses_partial_matches_and_street_level_results(monkeypatch):
    provider = mapping.GoogleMapProvider("test-key")
    components = [
        {"types": ["street_number"], "long_name": "123", "short_name": "123"},
        {"types": ["route"], "long_name": "Fake Drive", "short_name": "Fake Dr"},
        {"types": ["locality"], "long_name": "San Jose", "short_name": "San Jose"},
        {"types": ["administrative_area_level_1"], "long_name": "California", "short_name": "CA"},
        {"types": ["postal_code"], "long_name": "95192", "short_name": "95192"},
    ]
    place = {"lat": 37.33, "lng": -121.88}
    for result in (
        {"partial_match": True, "geometry": {"location_type": "ROOFTOP", "location": place}, "address_components": components},
        {"geometry": {"location_type": "GEOMETRIC_CENTER", "location": place}, "address_components": components},
        {"geometry": {"location_type": "APPROXIMATE", "location": place}, "address_components": components},
    ):
        monkeypatch.setattr(mapping, "_get_json", lambda _url, result=result: {"status": "OK", "results": [result]})
        assert provider.geocode("123 Fake Dr", "San Jose", "CA", "95192") is None

    monkeypatch.setattr(mapping, "_get_json", lambda _url: {"status": "OK", "results": [
        {"geometry": {"location_type": "ROOFTOP", "location": place}, "address_components": components}]})
    assert provider.geocode("123 Fake Dr", "San Jose", "CA", "95192") == mapping.GeoPoint(Decimal("37.330000"), Decimal("-121.880000"))
