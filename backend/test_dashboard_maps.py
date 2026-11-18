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


# An employee sees what is waiting, the vehicles and the trips, read-only and with no private details.
def test_employee_delivery_board_shows_waiting_orders_and_vehicles_without_private_data(customer, manager, employee):
    order_id = ready_order(customer, manager, weight='4.00')
    waiting_number = manager.get('/api/admin/delivery/queue').get_json()['orders'][0]['order_number']

    response = employee.get('/api/staff/delivery/board')

    assert response.status_code == 200
    board = response.get_json()
    assert [o['order_number'] for o in board['waiting']] == [waiting_number]
    assert set(board['waiting'][0]) == {'order_number', 'total_weight_lb', 'placed_at', 'waited_minutes'}
    assert {v['name'] for v in board['vehicles']} >= {'Robot 1', 'Robot 2'}
    assert all({'max_orders', 'max_weight_lb', 'status', 'current_trip_id'} <= set(v) for v in board['vehicles'])
    assert 'order_id' not in board['waiting'][0] and order_id


# Once an order is on a trip it leaves the waiting list and its vehicle shows the trip.
def test_employee_board_moves_an_order_from_waiting_to_its_vehicles_trip(customer, manager, employee):
    order_id, trip = create_trip(customer, manager)

    board = employee.get('/api/staff/delivery/board').get_json()

    assert board['waiting'] == []
    on_trip = [v for v in board['vehicles'] if v['current_trip_id'] == trip['trip_id']]
    assert len(on_trip) == 1 and on_trip[0]['name'] == trip['vehicle']['name']


# An order that cannot be scheduled is listed with its reason for employees.
def test_employee_board_lists_unschedulable_orders_with_the_reason(customer, manager, employee):
    ready_order(customer, manager, weight='4.00')
    with database.transaction() as cur:
        cur.execute("UPDATE orders SET unscheduled_reason = 'Address could not be found' WHERE status = 'awaiting_delivery'")

    problems = employee.get('/api/staff/delivery/board').get_json()['problems']

    assert [p['reason'] for p in problems] == ['Address could not be found']


# Managers can read the board too; customers and guests cannot, and employees still cannot manage deliveries.
def test_delivery_board_is_staff_only_and_read_only(customer, client, manager, employee):
    assert manager.get('/api/staff/delivery/board').status_code == 200
    assert customer.get('/api/staff/delivery/board').status_code == 403
    assert client.get('/api/staff/delivery/board').status_code == 401
    assert employee.post('/api/admin/delivery/trips', json={}).status_code == 403
    assert employee.get('/api/admin/delivery/vehicles').status_code == 403
    assert employee.post('/api/staff/delivery/board').status_code == 405
