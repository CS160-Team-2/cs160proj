"""MT7: precisely the same contract cases run against both real adapters,
with their HTTP boundary replaced by provider-shaped deterministic fakes."""
from decimal import Decimal

import pytest

from conftest import ready_order, requires_mysql
from services import mapping
from tests.mapping_contract_fixtures import adapter


@pytest.fixture(params=['google', 'mapbox'])
def maps(request, monkeypatch):
    provider, http = adapter(monkeypatch, request.param)
    return provider, http, request.param


def test_geocode_has_shared_coordinate_precision(maps):
    provider, _, _ = maps
    result = provider.geocode('200 E Santa Clara St', 'San Jose', 'CA', '95113')
    assert result == mapping.GeoPoint(Decimal('37.340000'), Decimal('-121.890000'))
    assert result.latitude.as_tuple().exponent == -6


def test_unfindable_address_returns_none(maps):
    provider, http, _ = maps; http.mode = 'not_found'
    assert provider.geocode('1 Nowhere St', 'San Jose', 'CA', '95113') is None


@pytest.mark.parametrize('operation', ['geocode', 'route'])
def test_outage_is_a_shared_mapping_error(maps, operation):
    provider, http, _ = maps; http.mode = 'down'
    with pytest.raises(mapping.MappingError, match='unavailable'):
        if operation == 'geocode': provider.geocode('1 Test St', 'San Jose', 'CA', '95113')
        else: provider.route(mapping.store_location(), [(1, mapping.store_location())])


@pytest.mark.parametrize('count', [1, 2, 10])
def test_routes_preserve_stops_coordinates_eta_and_return_leg(maps, count):
    provider, _, name = maps
    origin = mapping.store_location()
    stops = [(i, mapping.GeoPoint(Decimal('37.340000') + Decimal(i) / 1000, Decimal('-121.89')))
             for i in range(count)]
    result = provider.route(origin, stops)
    assert result.provider == name
    assert result.stop_order == list(reversed(range(count)))
    assert result.arrival_seconds == {key: 100 + index * 280 for index, key in enumerate(result.stop_order)}
    assert result.total_seconds == 100 * (count + 1) + 180 * count
    assert result.path[0] == result.path[-1] == [float(origin.latitude), float(origin.longitude)]
    assert all(-90 <= lat <= 90 and -180 <= lng <= 180 for lat, lng in result.path)


def test_no_route_is_a_shared_mapping_error(maps):
    provider, http, _ = maps; http.mode = 'no_route'
    with pytest.raises(mapping.MappingError):
        provider.route(mapping.store_location(), [(1, mapping.store_location())])


@requires_mysql
@pytest.mark.usefixtures('fresh_db')
def test_both_adapters_replan_outage_preserves_trip_and_addresses_are_not_guessed(maps, customer, manager):
    provider, http, _ = maps
    mapping.use_provider(provider)
    order_id = ready_order(customer, manager)
    created = manager.post('/api/admin/delivery/trips', json={'order_ids': [order_id]})
    assert created.status_code == 201, created.get_json()
    trip = created.get_json()['trip']; path = f"/api/admin/delivery/trips/{trip['trip_id']}"
    http.mode = 'down'
    assert manager.post(path + '/route').status_code == 502
    assert manager.get(path).get_json()['trip'] == trip
    http.mode = 'not_found'
    response = customer.post('/api/users/me/addresses', json={'street': '1 Nowhere St',
        'city': 'San Jose', 'state': 'CA', 'zip_code': '95113'})
    assert response.status_code == 422
    assert manager.get(path).get_json()['trip'] == trip
