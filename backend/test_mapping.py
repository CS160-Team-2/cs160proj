"""Contract tests for the mapping providers.  No network calls are made."""

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
            "results": [{"geometry": {"location": {
                "lat": 37.3371234,
                "lng": -121.8879876,
            }}}],
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
