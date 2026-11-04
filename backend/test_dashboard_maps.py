"""Role permissions, shared tracking, dispatch estimates and GPS validation."""
from datetime import datetime

import pytest

import db as database
from conftest import VEHICLE_TOKEN, ready_order, requires_mysql
from services import vehicle

pytestmark = [requires_mysql, pytest.mark.usefixtures('fresh_db')]


def create_trip(customer, manager):
    order_id = ready_order(customer, manager, weight='4.00')
    response = manager.post('/api/admin/delivery/trips', json={'order_ids': [order_id]})
    assert response.status_code == 201
    return order_id, response.get_json()['trip']


def test_employee_reads_delivery_map_but_cannot_manage_a_trip(customer, manager, employee):
    order_id, trip = create_trip(customer, manager)
    response = employee.get('/api/staff/delivery/trips')
    assert response.status_code == 200
    staff_trip = response.get_json()['trips'][0]
    assert staff_trip['route']['path'] == trip['route']['path']
    assert staff_trip['stops'][0]['order_id'] == order_id
    assert 'customer_name' not in staff_trip['stops'][0]
    assert 'address' not in staff_trip['stops'][0]
    assert employee.get('/api/admin/delivery/trips').status_code == 403
    assert employee.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch").status_code == 403


def test_customer_and_guest_cannot_read_staff_fleet(customer, client):
    assert customer.get('/api/staff/delivery/trips').status_code == 403
    assert client.get('/api/staff/delivery/trips').status_code == 401


def test_manager_can_inspect_tracking_without_a_customer_session(customer, manager, employee):
    order_id, trip = create_trip(customer, manager)
    response = manager.get(f'/api/admin/orders/{order_id}/tracking')
    assert response.status_code == 200
    assert response.get_json()['map']['destination']['latitude'] == trip['stops'][0]['latitude']
    assert 'path' not in response.get_json()['map']
    assert employee.get(f'/api/admin/orders/{order_id}/tracking').status_code == 403
    assert customer.get(f'/api/admin/orders/{order_id}/tracking').status_code == 403


def test_dispatch_rebases_an_old_arrival_estimate(customer, manager):
    _, trip = create_trip(customer, manager)
    original = datetime.fromisoformat(trip['stops'][0]['est_arrival'])
    with database.transaction() as cur:
        cur.execute('UPDATE delivery_trips SET route_planned_at = TIMESTAMPADD(MINUTE, -30, route_planned_at) WHERE trip_id = %s', (trip['trip_id'],))
        cur.execute('UPDATE trip_orders SET est_arrival = TIMESTAMPADD(MINUTE, -30, est_arrival) WHERE trip_id = %s', (trip['trip_id'],))
    response = manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    assert response.status_code == 200
    updated = response.get_json()['trip']['stops'][0]['est_arrival']
    assert -2 <= (datetime.fromisoformat(updated) - original).total_seconds() <= 15
    assert vehicle.link().sent[0]['stops'][0]['est_arrival'] == updated


def test_refused_dispatch_does_not_change_the_arrival_estimate(customer, manager):
    class RefusingVehicle(vehicle.SimulatedVehicleLink):
        def send_trip(self, vehicle, trip_id, stops):
            return False
    _, trip = create_trip(customer, manager)
    vehicle.use_link(RefusingVehicle(0))
    response = manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    assert response.status_code == 502
    restored = manager.get(f"/api/admin/delivery/trips/{trip['trip_id']}").get_json()['trip']
    assert restored['status'] == 'planned'
    assert restored['stops'][0]['est_arrival'] == trip['stops'][0]['est_arrival']


@pytest.mark.parametrize('coordinates', [
    {'latitude': '37.3'}, {'longitude': '-121.8'},
    {'latitude': '91', 'longitude': '0'}, {'latitude': '0', 'longitude': '-181'},
])
def test_incomplete_or_invalid_vehicle_positions_are_rejected(customer, manager, client, coordinates):
    _, trip = create_trip(customer, manager)
    manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    response = client.post(f"/api/fleet/trips/{trip['trip_id']}/status",
                           json={'status': 'en_route', **coordinates},
                           headers={'Authorization': f'Bearer {VEHICLE_TOKEN}'})
    assert response.status_code == 400
