"""M9: manage the simulated fleet without exposing vehicle credentials."""
import hashlib
import secrets
from decimal import Decimal

from flask import Blueprint

import db
from common import (MANAGER, ApiError, body, ok, require_decimal,
                    require_int, require_role, require_text)

admin_vehicles_bp = Blueprint('admin_vehicles', __name__)
FIELDS = {'name', 'max_orders', 'max_weight_lb', 'status'}


def _values(data, creating=False):
    if set(data) - FIELDS:
        raise ApiError('Only name, max_orders, max_weight_lb and status may be changed')
    values = {}
    if creating or 'name' in data:
        values['name'] = require_text(data, 'name', 60)
    if creating or 'max_orders' in data:
        try:
            number = require_int(data, 'max_orders', minimum=1)
        except OverflowError:
            raise ApiError('max_orders must be a finite whole number') from None
        if number > 10:
            raise ApiError('max_orders must not exceed the 10-order trip limit')
        values['max_orders'] = number
    if creating or 'max_weight_lb' in data:
        weight = require_decimal(data, 'max_weight_lb')
        if weight <= 0 or weight > 200 or weight != weight.quantize(Decimal('0.01')):
            raise ApiError('max_weight_lb must be above 0, at most 200, with at most two decimal places')
        values['max_weight_lb'] = weight
    if creating or 'status' in data:
        status = data.get('status', 'available')
        if status not in ('available', 'maintenance'):
            raise ApiError('status must be available or maintenance; dispatch controls on_trip')
        values['status'] = status
    if not values:
        raise ApiError('Provide at least one vehicle field')
    return values


def _safe_vehicle(cur, vehicle_id):
    cur.execute('SELECT vehicle_id, name, max_orders, max_weight_lb, status '
                'FROM vehicles WHERE vehicle_id = %s', (vehicle_id,))
    return {**cur.fetchone(), 'current_trip_id': None}


def _lock_fleet(cur):
    # Trip creation locks available vehicles too. Serialize mutations against
    # that choice so a trip cannot be assigned stale limits or a retired robot.
    cur.execute('SELECT vehicle_id FROM vehicles ORDER BY vehicle_id FOR UPDATE')
    return {row['vehicle_id'] for row in cur.fetchall()}


def _check_name(cur, values, vehicle_id=0):
    if 'name' not in values:
        return
    cur.execute('SELECT vehicle_id FROM vehicles WHERE name = %s AND vehicle_id <> %s',
                (values['name'], vehicle_id))
    if cur.fetchone():
        raise ApiError('A vehicle with that name already exists', 409, 'VEHICLE_NAME_TAKEN')


@admin_vehicles_bp.post('/api/admin/delivery/vehicles')
@require_role(*MANAGER)
def create_vehicle():
    values = _values(body(), creating=True)
    with db.transaction() as cur:
        _lock_fleet(cur)
        _check_name(cur, values)
        # New robots are simulated. Hardware token provisioning is separate;
        # internal credentials never appear in manager API responses.
        token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        cur.execute('INSERT INTO vehicles (name, max_orders, max_weight_lb, status, api_token_hash) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (values['name'], values['max_orders'], values['max_weight_lb'],
                     values['status'], token_hash))
        row = _safe_vehicle(cur, cur.lastrowid)
    return ok(201, vehicle=row)


@admin_vehicles_bp.patch('/api/admin/delivery/vehicles/<int:vehicle_id>')
@require_role(*MANAGER)
def edit_vehicle(vehicle_id):
    values = _values(body())
    with db.transaction() as cur:
        if vehicle_id not in _lock_fleet(cur):
            raise ApiError('No such vehicle', 404, 'NOT_FOUND')
        cur.execute("SELECT trip_id FROM delivery_trips WHERE vehicle_id = %s "
                    "AND status IN ('planned', 'out_for_delivery') LIMIT 1", (vehicle_id,))
        if cur.fetchone():
            raise ApiError('Finish the planned or dispatched trip before editing this vehicle',
                           409, 'VEHICLE_HAS_TRIP')
        _check_name(cur, values, vehicle_id)
        # Column names come only from FIELDS above, never from request text.
        assignments = ', '.join(f'{field} = %s' for field in values)
        cur.execute(f'UPDATE vehicles SET {assignments} WHERE vehicle_id = %s',
                    (*values.values(), vehicle_id))
        row = _safe_vehicle(cur, vehicle_id)
    return ok(vehicle=row)
