"""MT1-MT6, MB2/MB3/MB5: API invariants and remaining failure paths."""
import re
from decimal import Decimal

import pytest

import db
from common import ApiError
from conftest import (CUSTOMER, VEHICLE_TOKEN, error_code, ready_order,
                      requires_mysql, signed_in)
from order_status import change_status
from services import mapping, vehicle

pytestmark = [requires_mysql, pytest.mark.usefixtures('fresh_db')]


def trip_for(customer, manager, **payload):
    order_id = ready_order(customer, manager)
    result = manager.post('/api/admin/delivery/trips', json={'order_ids': [order_id], **payload})
    assert result.status_code == 201, result.get_json()
    return order_id, result.get_json()['trip']


def state(order_id):
    return db.query_one('SELECT status FROM orders WHERE order_id=%s', (order_id,))['status']


def test_mt1_invalid_direct_step_writes_no_history(customer, manager):
    order_id = ready_order(customer, manager)
    before = db.query_one('SELECT COUNT(*) n FROM order_status_history')['n']
    with pytest.raises(ApiError) as caught:
        with db.transaction() as cur:
            change_status(cur, order_id, 'awaiting_delivery', 'delivered', 3, 'staff')
    assert caught.value.code == 'INVALID_STATUS_CHANGE'
    assert state(order_id) == 'awaiting_delivery'
    assert db.query_one('SELECT COUNT(*) n FROM order_status_history')['n'] == before


def test_mt1_stale_expected_status_is_a_conflict_without_history(customer, manager):
    order_id = ready_order(customer, manager)
    before = db.query_one('SELECT COUNT(*) n FROM order_status_history')['n']
    with pytest.raises(ApiError) as caught:
        with db.transaction() as cur:
            change_status(cur, order_id, 'placed', 'awaiting_delivery', 3, 'staff')
    assert caught.value.code == 'ORDER_CHANGED'
    assert db.query_one('SELECT COUNT(*) n FROM order_status_history')['n'] == before


@pytest.mark.parametrize('count,total,accepted', [(9, 199, True), (10, 200, True),
    (11, 199, False), (9, 201, False), (10, 201, False), (11, 200, False)])
def test_mt2_api_checks_both_capacity_boundaries(customer, manager, count, total, accepted):
    weights = [Decimal('1')] * (count - 1) + [Decimal(total) - (count - 1)]
    ids = [ready_order(customer, manager, str(w)) for w in weights]
    result = manager.post('/api/admin/delivery/trips', json={'order_ids': ids})
    assert result.status_code == (201 if accepted else 409), result.get_json()
    if accepted:
        trip = result.get_json()['trip']
        assert trip['order_count'] == count and Decimal(trip['total_weight_lb']) == total
        assert trip['capacity_problem'] is None
    else:
        assert error_code(result) == 'CAPACITY_EXCEEDED'
        assert all(state(i) == 'awaiting_delivery' for i in ids)
        assert db.query_one('SELECT COUNT(*) n FROM delivery_trips')['n'] == 0


def test_mt2_overweight_order_is_left_with_capacity_reason(customer, manager):
    too_heavy = ready_order(customer, manager, '201')
    good = ready_order(customer, manager, '199')
    result = manager.post('/api/admin/delivery/trips', json={})
    assert result.status_code == 201
    assert result.get_json()['trip']['stops'][0]['order_id'] == good
    assert state(too_heavy) == 'awaiting_delivery'
    assert 'Too heavy' in db.query_one('SELECT unscheduled_reason FROM orders WHERE order_id=%s', (too_heavy,))['unscheduled_reason']


@pytest.mark.parametrize('payload,code', [({'vehicle_id': 999}, 'NOT_FOUND'),
    ({'order_ids': []}, 'BAD_REQUEST'), ({'order_ids': '1'}, 'BAD_REQUEST'),
    ({'order_ids': [1, 1]}, 'BAD_REQUEST'), ({'order_ids': [999]}, 'ORDER_NOT_WAITING')])
def test_mt3_invalid_trip_selection_changes_nothing(customer, manager, payload, code):
    ready_order(customer, manager)
    result = manager.post('/api/admin/delivery/trips', json=payload)
    assert error_code(result) == code
    assert db.query_one('SELECT COUNT(*) n FROM delivery_trips')['n'] == 0


def test_mt3_no_free_vehicle_exceptions_and_missing_trip(manager, customer):
    ready_order(customer, manager)
    with db.transaction() as cur:
        cur.execute("UPDATE vehicles SET status='maintenance'")
    assert error_code(manager.post('/api/admin/delivery/trips', json={})) == 'NO_VEHICLE_FREE'
    assert manager.get('/api/admin/delivery/exceptions').get_json()['orders'][0]['reason'] == 'No vehicle is free right now'
    assert manager.get('/api/admin/delivery/trips/999').status_code == 404
    assert manager.get('/api/admin/delivery/trips?status=invalid').status_code == 400


def test_mt3_editing_failures_and_empty_trip(customer, manager):
    order_id, trip = trip_for(customer, manager)
    path = f"/api/admin/delivery/trips/{trip['trip_id']}"
    assert error_code(manager.post(path + '/orders', json={'order_id': order_id})) == 'ORDER_NOT_WAITING'
    assert error_code(manager.delete(path + '/orders/999')) == 'NOT_ON_TRIP'
    assert manager.delete(path + f'/orders/{order_id}').get_json()['route_error'] is None
    assert error_code(manager.post(path + '/dispatch')) == 'TRIP_EMPTY'
    assert error_code(manager.post(path + '/route')) == 'ROUTE_FAILED'
    assert state(order_id) == 'awaiting_delivery'


def test_mt3_adding_to_left_trip_is_refused(customer, manager):
    _, trip = trip_for(customer, manager)
    pending = ready_order(customer, manager)
    path = f"/api/admin/delivery/trips/{trip['trip_id']}"
    assert manager.post(path + '/dispatch').status_code == 200
    assert error_code(manager.post(path + '/orders', json={'order_id': pending})) == 'TRIP_ALREADY_DISPATCHED'
    assert state(pending) == 'awaiting_delivery'


@pytest.mark.parametrize('change,code', [({'max_orders': 0}, 'CAPACITY_EXCEEDED'),
    ({'status': 'maintenance'}, 'VEHICLE_BUSY')])
def test_mt3_dispatch_rechecks_vehicle_and_rolls_back(customer, manager, change, code):
    order_id, trip = trip_for(customer, manager)
    with db.transaction() as cur:
        if 'max_orders' in change:
            # A second order makes a later lower capacity invalid; normal
            # vehicle edits are blocked while assigned, so emulate old data.
            cur.execute('UPDATE vehicles SET max_weight_lb=0.50 WHERE vehicle_id=1')
        else:
            cur.execute("UPDATE vehicles SET status='maintenance' WHERE vehicle_id=1")
    result = manager.post(f"/api/admin/delivery/trips/{trip['trip_id']}/dispatch")
    assert error_code(result) == code
    assert state(order_id) == 'assigned_to_trip'
    assert db.query_one('SELECT started_at FROM delivery_trips WHERE trip_id=%s', (trip['trip_id'],))['started_at'] is None


def test_mt3_route_failure_during_create_add_and_remove(customer, manager):
    class Down(mapping.FakeMapProvider):
        def route(self, origin, stops):
            raise mapping.MappingError('Mapping unavailable')
    first = ready_order(customer, manager)
    second = ready_order(customer, manager)
    mapping.use_provider(Down())
    created = manager.post('/api/admin/delivery/trips', json={'order_ids': [first]}).get_json()
    assert created['route_error'] == 'Mapping unavailable'
    path = f"/api/admin/delivery/trips/{created['trip']['trip_id']}"
    assert error_code(manager.post(path + '/dispatch')) == 'NO_ROUTE'
    assert manager.post(path + '/orders', json={'order_id': second}).get_json()['route_error']
    assert manager.delete(path + f'/orders/{first}').get_json()['route_error']
    assert state(first) == 'awaiting_delivery' and state(second) == 'assigned_to_trip'


def test_mb5_provider_change_requires_replan_before_dispatch(customer, manager):
    order_id, trip = trip_for(customer, manager)
    path = f"/api/admin/delivery/trips/{trip['trip_id']}"
    class NewProvider(mapping.FakeMapProvider):
        def route(self, origin, stops):
            route = super().route(origin, stops); route.provider = 'mapbox'; return route
    provider = NewProvider()
    # The service's configured identity is isolated from outbound HTTP.
    from unittest.mock import patch
    mapping.use_provider(provider)
    with patch.object(mapping, 'provider_name', return_value='mapbox'):
        assert manager.get(path).get_json()['trip']['route_provider_changed'] is True
        assert error_code(manager.post(path + '/dispatch')) == 'ROUTE_PROVIDER_CHANGED'
        assert state(order_id) == 'assigned_to_trip'
        assert manager.post(path + '/route').status_code == 200
        assert manager.get(path).get_json()['trip']['route_provider_changed'] is False
        assert manager.post(path + '/dispatch').status_code == 200


def test_mb3_deleted_customer_is_readable_without_placeholder_and_address_is_kept(customer, manager):
    order_id, trip = trip_for(customer, manager)
    path = f"/api/admin/delivery/trips/{trip['trip_id']}"
    manager.post(path + '/dispatch')
    assert manager.patch(f'/api/admin/orders/{order_id}/status', json={'status': 'delivered'}).status_code == 200
    old = manager.get(f'/api/admin/orders/{order_id}').get_json()['order']['address']
    assert customer.delete('/api/users/me', json={'password': CUSTOMER[1]}).status_code == 200
    listed = manager.get('/api/admin/orders').get_json()['orders'][0]
    detail = manager.get(f'/api/admin/orders/{order_id}').get_json()['order']
    assert listed['customer_name'] == detail['customer']['full_name'] == 'Deleted customer'
    assert listed['customer_email'] is None and detail['customer']['email'] is None
    assert detail['address'] == old
    stop = manager.get(path).get_json()['trip']['stops'][0]
    assert stop['customer_name'] == 'Deleted customer' and old['street'] in stop['address']
    assert customer.get('/api/admin/orders').status_code == 401


def test_mt4_missing_order_detail_payments_and_tracking_return_404(customer, manager):
    for suffix in ('', '/payments', '/tracking'):
        assert manager.get('/api/admin/orders/999' + suffix).status_code == 404
    assert manager.get('/api/admin/orders?status=unknown').status_code == 400
    assert manager.get('/api/admin/orders', query_string={'q': 'x' * 256}).status_code == 400
    order_id = ready_order(customer, manager)
    assert manager.patch(f'/api/admin/orders/{order_id}/status', json={'status': 'unknown'}).status_code == 400


def test_mt3_list_filters_show_current_trips_and_schedulable_orders_are_not_exceptions(customer, manager):
    first = ready_order(customer, manager)
    assert manager.get('/api/admin/delivery/exceptions').get_json()['orders'] == []
    one = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 1, 'order_ids': [first]}).get_json()['trip']['trip_id']
    second = ready_order(customer, manager)
    two = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 2, 'order_ids': [second]}).get_json()['trip']['trip_id']
    assert manager.post(f'/api/admin/delivery/trips/{one}/dispatch').status_code == 200
    def ids(status=None):
        response = manager.get('/api/admin/delivery/trips', query_string={'status': status} if status else {})
        assert response.status_code == 200
        return [trip['trip_id'] for trip in response.get_json()['trips']]
    assert ids() == [two, one]
    assert ids('planned') == [two] and ids('out_for_delivery') == [one] and ids('completed') == []
    assert manager.patch(f'/api/admin/orders/{first}/status', json={'status': 'delivered'}).status_code == 200
    assert ids('completed') == [one]


def test_mt5_every_admin_staff_and_fleet_route_has_role_checks(app, request, manager):
    from conftest import EMPLOYEE
    clients = {'visitor': app.test_client(), 'customer': signed_in(app, *CUSTOMER),
               'employee': signed_in(app, *EMPLOYEE), 'manager': manager}
    staff_prefixes = ('/api/admin/products',)
    staff_inventory = {'/api/admin/inventory', '/api/admin/inventory/low-stock',
                       '/api/admin/inventory/<int:product_id>', '/api/admin/inventory/<int:product_id>/changes'}
    checked = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(('/api/admin/', '/api/staff/', '/api/fleet/')):
            continue
        path = re.sub(r'<(?:[^:<>]+:)?([^<>]+)>', lambda m: 'missing.jpg' if m[1] == 'filename' else '999', rule.rule)
        allowed_staff = rule.rule.startswith(staff_prefixes) or rule.rule in staff_inventory or rule.rule.startswith('/api/staff/')
        for method in sorted(rule.methods - {'OPTIONS', 'HEAD'}):
            for role, client in clients.items():
                if rule.rule.startswith('/api/fleet/'):
                    expected = 401  # A person session cannot replace a vehicle token.
                elif role == 'visitor': expected = 401
                elif role == 'customer': expected = 403
                elif role == 'employee' and not allowed_staff: expected = 403
                else: continue  # Success/validation tested with real fixtures elsewhere.
                response = client.open(path, method=method, json={})
                assert response.status_code == expected, (method, rule.rule, role, response.get_json())
            checked.add((method, rule.rule))
    assert len(checked) >= 30
    assert employee_staff_read(app, clients['employee'])


def employee_staff_read(app, employee):
    response = employee.get('/api/staff/delivery/trips')
    return response.status_code == 200
