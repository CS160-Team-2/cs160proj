from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

import db
from conftest import ready_order, requires_mysql
from services import vehicle

pytestmark = [requires_mysql, pytest.mark.usefixtures('fresh_db')]


def running_trip(customer, manager, count=1):
    with db.transaction() as cur:
        cur.execute('UPDATE addresses SET latitude=37.36, longitude=-121.91 WHERE address_id=1')
    ids = [ready_order(customer, manager) for _ in range(count)]
    created = manager.post('/api/admin/delivery/trips', json={'order_ids': ids})
    trip = created.get_json()['trip']; trip_id = trip['trip_id']
    assert manager.post(f'/api/admin/delivery/trips/{trip_id}/dispatch').status_code == 200
    return trip_id, ids


def test_simulator_reports_road_progress_and_completes_from_persisted_clock(customer, manager):
    trip_id, ids = running_trip(customer, manager)
    with db.transaction() as cur:
        cur.execute('UPDATE delivery_trips SET started_at=TIMESTAMPADD(SECOND,-4,NOW()) WHERE trip_id=%s', (trip_id,))
    first_worker = vehicle.SimulatedVehicleLink(10)
    first_worker.tick(trip_id)
    first = db.query_one('SELECT * FROM delivery_trips WHERE trip_id=%s', (trip_id,))
    assert first['last_report'] == 'en_route'
    assert 37.3352 < float(first['last_latitude']) < 37.36
    assert -121.91 < float(first['last_longitude']) < -121.8811
    with db.transaction() as cur:
        cur.execute('UPDATE delivery_trips SET started_at=TIMESTAMPADD(SECOND,-20,NOW()) WHERE trip_id=%s', (trip_id,))
    vehicle.SimulatedVehicleLink(10).tick(trip_id)
    trip = db.query_one('SELECT * FROM delivery_trips WHERE trip_id=%s', (trip_id,))
    assert trip['status'] == trip['last_report'] == 'completed'
    assert float(trip['last_latitude']) == 37.36
    assert db.query_one('SELECT status FROM vehicles WHERE vehicle_id=1')['status'] == 'available'
    assert db.query_one('SELECT status FROM orders WHERE order_id=%s', (ids[0],))['status'] == 'delivered'


def test_simulator_never_replays_a_completed_stop_or_overwrites_finished_trip(customer, manager):
    trip_id, ids = running_trip(customer, manager, 2)
    assert manager.patch(f'/api/admin/orders/{ids[0]}/status', json={'status': 'delivered'}).status_code == 200
    with db.transaction() as cur:
        cur.execute('UPDATE trip_orders SET delivered_at=TIMESTAMPADD(SECOND,-20,NOW()) WHERE order_id=%s', (ids[0],))
    def tick(_): vehicle.SimulatedVehicleLink(10).tick(trip_id)
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(tick, range(2)))
    assert db.query_one("SELECT COUNT(*) n FROM order_status_history WHERE to_status='delivered'")['n'] == 2
    before = db.query_one('SELECT * FROM delivery_trips WHERE trip_id=%s', (trip_id,))
    vehicle.SimulatedVehicleLink(10).tick(trip_id)
    assert db.query_one('SELECT * FROM delivery_trips WHERE trip_id=%s', (trip_id,)) == before


def test_disabled_simulation_and_missing_route_do_not_complete_orders(customer, manager):
    trip_id, ids = running_trip(customer, manager)
    with db.transaction() as cur:
        cur.execute('UPDATE delivery_trips SET started_at=TIMESTAMPADD(SECOND,-30,NOW()) WHERE trip_id=%s', (trip_id,))
    vehicle.SimulatedVehicleLink(0).tick(trip_id)
    with db.transaction() as cur: cur.execute('UPDATE delivery_trips SET route_json=NULL WHERE trip_id=%s', (trip_id,))
    vehicle.SimulatedVehicleLink(1).tick(trip_id)
    assert db.query_one('SELECT status FROM orders WHERE order_id=%s', (ids[0],))['status'] == 'out_for_delivery'


def wait_for(check, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check(): return
        time.sleep(.1)
    raise AssertionError('The persisted simulator did not reach the expected state')


def test_real_flask_process_restart_resumes_without_any_http_request(customer, manager, tmp_path):
    trip_id, ids = running_trip(customer, manager)
    environment = {**os.environ, 'VEHICLE_LINK': 'simulated', 'VEHICLE_SIMULATION_SECONDS': '4',
                   'MYSQL_DATABASE': db.DB_CONFIG['database']}
    command = [sys.executable, '-c', 'from app import app; import threading; threading.Event().wait()']
    process = None
    with (tmp_path / 'simulation.log').open('w') as log:
        try:
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parent.parent, env=environment, stdout=log, stderr=log)
            wait_for(lambda: db.query_one('SELECT last_report FROM delivery_trips WHERE trip_id=%s', (trip_id,))['last_report'] == 'en_route')
            process.terminate(); process.wait(timeout=5)
            checkpoint = db.query_one('SELECT * FROM delivery_trips WHERE trip_id=%s', (trip_id,))
            assert checkpoint['status'] == 'out_for_delivery'
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parent.parent, env=environment, stdout=log, stderr=log)
            wait_for(lambda: db.query_one('SELECT status FROM delivery_trips WHERE trip_id=%s', (trip_id,))['status'] == 'completed')
            assert process.poll() is None
        finally:
            if process is not None and process.poll() is None:
                process.terminate(); process.wait(timeout=5)
    assert db.query_one("SELECT COUNT(*) n FROM order_status_history WHERE order_id=%s AND to_status='delivered'", (ids[0],))['n'] == 1
    assert db.query_one('SELECT status FROM vehicles WHERE vehicle_id=1')['status'] == 'available'
