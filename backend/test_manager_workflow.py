"""M5/M6/M7/M9: real Flask requests, MySQL state, and role boundaries."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import pytest

import db
from conftest import (APPLES_ID, CUSTOMER, MANAGER, buy, new_key,
                      ready_order, requires_mysql, signed_in)

pytestmark = [requires_mysql, pytest.mark.usefixtures('fresh_db')]


def order_rows(count=5):
    with db.transaction() as cur:
        for i in range(count):
            cur.execute("INSERT INTO orders (order_number, user_id, address_id, status, subtotal, tax, "
                        "delivery_fee, total_weight_lb, grand_total, idempotency_key, placed_at) "
                        "VALUES (%s, 1, 1, %s, 1, 0, 0, 1, 1, %s, '2026-11-10 12:00:00')",
                        (f'OFS-PAGE-{i:04}', 'placed' if i % 2 == 0 else 'awaiting_delivery', new_key()))


def dispatched(customer, manager, count=2):
    ids = [ready_order(customer, manager) for _ in range(count)]
    result = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 1, 'order_ids': ids})
    assert result.status_code == 201, result.get_json()
    trip_id = result.get_json()['trip']['trip_id']
    assert manager.post(f'/api/admin/delivery/trips/{trip_id}/dispatch').status_code == 200
    return trip_id, ids


def test_problems_include_preorder_decline_and_only_safe_payment_fields(customer, manager):
    assert buy(customer, {APPLES_ID: 1}, token='tok_declined').status_code == 402
    payload = manager.get('/api/admin/problems').get_json()
    assert payload['pagination']['total'] == 1
    row = payload['problems'][0]
    assert row['kind'] == 'declined' and row['order_id'] is None and row['order_number'] is None
    assert row['transaction_id'] > 0 and row['reason'] and row['occurred_at']
    assert set(row) == {'problem_id', 'kind', 'occurred_at', 'time_label', 'order_id',
                        'order_number', 'transaction_id', 'gateway_ref', 'amount', 'card_last4', 'reason'}
    assert row['time_label'] == 'Payment recorded'
    assert isinstance(row['amount'], str)


def test_problems_link_retry_to_order_and_include_recorded_refund(customer, manager):
    key = new_key()
    assert buy(customer, {APPLES_ID: 1}, token='tok_declined', key=key).status_code == 402
    approved = customer.post('/api/orders', json={'address_id': 1, 'payment_token': 'tok_visa',
                                                'idempotency_key': key})
    order = approved.get_json()['order']
    with db.transaction() as cur:
        cur.execute("INSERT INTO payments (order_id, user_id, idempotency_key, amount, status, gateway_ref) "
                    "VALUES (%s, 1, %s, 1, 'refunded', 'refund-reference')", (order['order_id'], new_key()))
    rows = manager.get('/api/admin/problems').get_json()['problems']
    assert {r['kind'] for r in rows} == {'declined', 'refunded'}
    assert all(r['order_number'] == order['order_number'] for r in rows)
    assert next(r for r in rows if r['kind'] == 'refunded')['reason'] == 'Refund recorded'


def test_problems_surface_approved_charge_when_checkout_compensation_failed(manager):
    with db.transaction() as cur:
        cur.execute("INSERT INTO payments (user_id, idempotency_key, amount, status, gateway_ref, failure_reason) "
                    "VALUES (1, %s, 10, 'approved', 'charge-needs-review', %s)",
                    (new_key(), 'Order failed and the automatic refund did not go through'))
    rows = manager.get('/api/admin/problems?kind=payment_review').get_json()['problems']
    assert len(rows) == 1 and rows[0]['gateway_ref'] == 'charge-needs-review'
    assert rows[0]['kind'] == 'payment_review' and rows[0]['order_id'] is None


def test_problem_filters_pagination_and_date_boundaries(manager):
    with db.transaction() as cur:
        for i, date in enumerate(('2026-11-09 23:59:59', '2026-11-10 00:00:00',
                                  '2026-11-10 23:59:59', '2026-11-11 00:00:00')):
            cur.execute("INSERT INTO payments (user_id, idempotency_key, amount, status, created_at) "
                        "VALUES (1, %s, 1, 'declined', %s)", (new_key(), date))
    path = '/api/admin/problems?kind=declined&from=2026-11-10&to=2026-11-10&per_page=1'
    first = manager.get(path).get_json()
    second = manager.get(path + '&page=2').get_json()
    assert first['pagination'] == {'page': 1, 'per_page': 1, 'total': 2, 'total_pages': 2}
    assert first['problems'][0]['occurred_at'] > second['problems'][0]['occurred_at']
    assert manager.get('/api/admin/problems?kind=refunded').get_json()['problems'] == []


def test_scheduling_problems_are_current_and_use_honest_timestamp(customer, manager):
    order_id = ready_order(customer, manager)
    with db.transaction() as cur:
        cur.execute('UPDATE orders SET unscheduled_reason = %s WHERE order_id = %s',
                    ('Mapping provider unavailable', order_id))
    rows = manager.get('/api/admin/problems?kind=unscheduled').get_json()['problems']
    assert len(rows) == 1 and rows[0]['reason'] == 'Mapping provider unavailable'
    assert rows[0]['time_label'] == 'Order placed'
    assert rows[0]['order_id'] == order_id
    assert manager.post('/api/admin/delivery/trips', json={'order_ids': [order_id]}).status_code == 201
    assert manager.get('/api/admin/problems?kind=unscheduled').get_json()['problems'] == []


def test_problems_explain_no_available_vehicle(customer, manager):
    ready_order(customer, manager)
    with db.transaction() as cur:
        cur.execute("UPDATE vehicles SET status = 'maintenance'")
    row = manager.get('/api/admin/problems').get_json()['problems'][0]
    assert row['reason'] == 'No vehicle is free right now'


@pytest.mark.parametrize('query', ['kind=approved', 'from=bad', 'to=2026-02-30',
                                    'from=2026-11-11&to=2026-11-10',
                                    'page=0', 'per_page=101', 'page=1.5', 'page=-1'])
def test_problem_query_validation(manager, query):
    assert manager.get('/api/admin/problems?' + query).status_code == 400


def test_order_pages_are_stable_disjoint_and_keep_global_status_counts(manager):
    order_rows(7)
    first = manager.get('/api/admin/orders?page=1&per_page=3').get_json()
    second = manager.get('/api/admin/orders?page=2&per_page=3').get_json()
    last = manager.get('/api/admin/orders?page=3&per_page=3').get_json()
    assert first['pagination'] == {'page': 1, 'per_page': 3, 'total': 7, 'total_pages': 3}
    ids = [r['order_id'] for data in (first, second, last) for r in data['orders']]
    assert len(set(ids)) == 7 and ids == sorted(ids, reverse=True)
    assert first['status_counts']['placed'] == 4
    assert first['status_counts']['awaiting_delivery'] == 3
    assert first['status_counts'] == second['status_counts'] == last['status_counts']


def test_paged_search_dates_and_status_are_all_applied_on_server(manager):
    order_rows(7)
    path = '/api/admin/orders?q=customer%40ofs.test&from=2026-11-10&to=2026-11-10&status=placed&per_page=2'
    reply = manager.get(path).get_json()
    assert reply['pagination']['total'] == 4
    assert len(reply['orders']) == 2
    assert all(row['status'] == 'placed' for row in reply['orders'])
    assert reply['status_counts']['awaiting_delivery'] == 3
    assert manager.get(path.replace('2026-11-10', '2026-11-09')).get_json()['orders'] == []


def test_page_clamps_after_results_shrink_and_empty_pages_are_valid(manager):
    order_rows(5)
    reply = manager.get('/api/admin/orders?page=999&per_page=2').get_json()
    assert reply['pagination']['page'] == 3 and len(reply['orders']) == 1
    with db.transaction() as cur:
        cur.execute("UPDATE orders SET status='delivered'")
    reply = manager.get('/api/admin/orders?page=3&per_page=2&status=placed').get_json()
    assert reply['pagination'] == {'page': 1, 'per_page': 2, 'total': 0, 'total_pages': 1}
    assert reply['orders'] == []


@pytest.mark.parametrize('query', ['page=0', 'page=abc', 'page=1.5', 'per_page=0',
                                    'per_page=101', 'page=1000000000', 'page='])
def test_order_pagination_rejects_invalid_values(manager, query):
    assert manager.get('/api/admin/orders?' + query).status_code == 400


def test_legacy_order_list_contract_is_preserved(manager):
    order_rows(30)
    reply = manager.get('/api/admin/orders').get_json()
    assert len(reply['orders']) == 30 and 'pagination' not in reply


def test_demo_recovery_survives_new_application_and_is_audited_and_idempotent(customer, manager, monkeypatch):
    monkeypatch.setenv('VEHICLE_LINK', 'simulated')
    trip_id, ids = dispatched(customer, manager)
    # The new Flask app has no request/session/timer state from the old one.
    from app import create_app
    from services import vehicle
    vehicle.use_link(vehicle.SimulatedVehicleLink(0))
    fresh_app = create_app()
    fresh_app.config['TESTING'] = True
    restarted_manager = signed_in(fresh_app, *MANAGER)
    path = f'/api/admin/delivery/trips/{trip_id}/simulation/stops/{ids[0]}/complete'
    for _ in range(2):
        reply = restarted_manager.post(path, json={'confirmed': True})
        assert reply.status_code == 200, reply.get_json()
        assert reply.get_json()['trip']['status'] == 'out_for_delivery'
    rows = db.query_all("SELECT * FROM order_status_history WHERE order_id=%s AND to_status='delivered'", (ids[0],))
    assert len(rows) == 1 and rows[0]['source'] == 'simulation_recovery' and rows[0]['changed_by'] == 3
    other = db.query_one('SELECT delivered_at FROM trip_orders WHERE order_id=%s', (ids[1],))
    assert other['delivered_at'] is None
    last = restarted_manager.post(path.replace(f'/{ids[0]}/complete', f'/{ids[1]}/complete'), json={'confirmed': True})
    assert last.get_json()['trip']['status'] == 'completed'
    assert last.get_json()['trip']['last_report'] == 'demo_trip_completed'
    assert db.query_one('SELECT status FROM vehicles WHERE vehicle_id=1')['status'] == 'available'
    customer_again = signed_in(fresh_app, *CUSTOMER)
    number = last.get_json()['trip']['stops'][0]['order_number']
    assert customer_again.get(f'/api/orders/{number}/tracking').get_json()['status'] == 'delivered'


def test_demo_recovery_rejects_unconfirmed_planned_missing_and_real_vehicle(customer, manager, monkeypatch):
    monkeypatch.setenv('VEHICLE_LINK', 'simulated')
    order_id = ready_order(customer, manager)
    trip_id = manager.post('/api/admin/delivery/trips', json={'order_ids': [order_id]}).get_json()['trip']['trip_id']
    path = f'/api/admin/delivery/trips/{trip_id}/simulation/stops/{order_id}/complete'
    assert manager.post(path, json={}).status_code == 400
    assert manager.post(path, json={'confirmed': 'true'}).status_code == 400
    assert manager.post(path, json={'confirmed': True}).status_code == 409
    assert manager.post(path.replace(f'/stops/{order_id}', '/stops/999'), json={'confirmed': True}).status_code == 404
    assert manager.post(path.replace(f'/trips/{trip_id}', '/trips/999'), json={'confirmed': True}).status_code == 404
    monkeypatch.setenv('VEHICLE_LINK', 'hardware')
    assert manager.post(path, json={'confirmed': True}).get_json()['error']['code'] == 'NOT_SIMULATED'


def test_concurrent_demo_completion_records_one_history_entry(app, customer, manager, monkeypatch):
    monkeypatch.setenv('VEHICLE_LINK', 'simulated')
    trip_id, ids = dispatched(customer, manager, count=1)
    clients = [signed_in(app, *MANAGER), signed_in(app, *MANAGER)]
    path = f'/api/admin/delivery/trips/{trip_id}/simulation/stops/{ids[0]}/complete'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: client.post(path, json={'confirmed': True}).status_code, clients))
    assert results == [200, 200]
    assert db.query_one("SELECT COUNT(*) n FROM order_status_history WHERE order_id=%s AND to_status='delivered'", (ids[0],))['n'] == 1
    assert db.query_one('SELECT status FROM vehicles WHERE vehicle_id=1')['status'] == 'available'


VEHICLE = {'name': 'Robot 3', 'max_orders': 8, 'max_weight_lb': '150.25', 'status': 'available'}


def test_vehicle_create_edit_list_privacy_and_maintenance(manager):
    result = manager.post('/api/admin/delivery/vehicles', json=VEHICLE)
    assert result.status_code == 201, result.get_json()
    robot = result.get_json()['vehicle']
    safe = {'vehicle_id', 'name', 'max_orders', 'max_weight_lb', 'status', 'current_trip_id'}
    assert set(robot) == safe and robot['max_weight_lb'] == '150.25'
    hashed = db.query_one('SELECT api_token_hash FROM vehicles WHERE vehicle_id=%s', (robot['vehicle_id'],))
    assert len(hashed['api_token_hash']) == 64
    result = manager.patch(f"/api/admin/delivery/vehicles/{robot['vehicle_id']}", json={'status': 'maintenance', 'name': 'Spare robot'})
    assert result.status_code == 200
    assert result.get_json()['vehicle']['status'] == 'maintenance'
    listed = manager.get('/api/admin/delivery/vehicles').get_json()['vehicles']
    assert all(set(row) == safe for row in listed)
    assert manager.patch(f"/api/admin/delivery/vehicles/{robot['vehicle_id']}", json={'status': 'available'}).status_code == 200


@pytest.mark.parametrize('change', [
    {'name': ''}, {'name': 'x' * 61}, {'max_orders': 0}, {'max_orders': 11},
    {'max_orders': True}, {'max_orders': 1.5}, {'max_orders': float('inf')},
    {'max_orders': float('-inf')}, {'max_weight_lb': '0'},
    {'max_weight_lb': '200.01'}, {'max_weight_lb': '1.001'}, {'max_weight_lb': 'NaN'},
    {'max_weight_lb': '-1'}, {'status': 'on_trip'}, {'api_token_hash': 'injected'},
])
def test_vehicle_validation_creates_nothing_and_invalid_edits_preserve_values(manager, change):
    assert manager.post('/api/admin/delivery/vehicles', json={**VEHICLE, **change}).status_code == 400
    assert manager.patch('/api/admin/delivery/vehicles/1', json=change).status_code == 400
    assert db.query_one('SELECT COUNT(*) n FROM vehicles')['n'] == 2
    assert db.query_one('SELECT max_weight_lb FROM vehicles WHERE vehicle_id=1')['max_weight_lb'] == Decimal('200')


def test_vehicle_duplicate_missing_and_empty_edit(manager):
    assert manager.post('/api/admin/delivery/vehicles', json={**VEHICLE, 'name': 'robot 1'}).status_code == 409
    assert manager.patch('/api/admin/delivery/vehicles/1', json={'name': 'Robot 2'}).status_code == 409
    assert manager.patch('/api/admin/delivery/vehicles/999', json={'name': 'Robot 3'}).status_code == 404
    assert manager.patch('/api/admin/delivery/vehicles/1', json={}).status_code == 400


def test_vehicle_limits_used_for_assignment_and_active_vehicle_edits_refused(customer, manager):
    assert manager.patch('/api/admin/delivery/vehicles/1', json={'max_weight_lb': '5', 'max_orders': 1}).status_code == 200
    ids = [ready_order(customer, manager, weight='3') for _ in range(2)]
    result = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 1, 'order_ids': ids})
    assert result.status_code == 409
    trip_id = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 1, 'order_ids': ids[:1]}).get_json()['trip']['trip_id']
    for changes in ({'max_orders': 10}, {'status': 'maintenance'}, {'name': 'Different robot'}):
        reply = manager.patch('/api/admin/delivery/vehicles/1', json=changes)
        assert reply.status_code == 409 and reply.get_json()['error']['code'] == 'VEHICLE_HAS_TRIP'
    assert manager.post(f'/api/admin/delivery/trips/{trip_id}/dispatch').status_code == 200
    assert manager.patch('/api/admin/delivery/vehicles/1', json={'status': 'available'}).status_code == 409


def test_maintenance_vehicle_cannot_be_assigned(customer, manager):
    order_id = ready_order(customer, manager)
    assert manager.patch('/api/admin/delivery/vehicles/1', json={'status': 'maintenance'}).status_code == 200
    reply = manager.post('/api/admin/delivery/trips', json={'vehicle_id': 1, 'order_ids': [order_id]})
    assert reply.status_code == 409 and reply.get_json()['error']['code'] == 'VEHICLE_BUSY'


@pytest.mark.parametrize('role,expected', [('customer', 403), ('employee', 403), ('visitor', 401)])
def test_new_manager_actions_are_not_public(request, role, expected):
    client = request.getfixturevalue('client' if role == 'visitor' else role)
    checks = [
        client.get('/api/admin/problems'),
        client.get('/api/admin/orders?page=1'),
        client.get('/api/admin/delivery/vehicles'),
        client.post('/api/admin/delivery/vehicles', json=VEHICLE),
        client.patch('/api/admin/delivery/vehicles/1', json={'name': 'Forbidden'}),
        client.post('/api/admin/delivery/trips/1/simulation/stops/1/complete', json={'confirmed': True}),
    ]
    assert all(response.status_code == expected for response in checks)
