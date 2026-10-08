"""Delivery management (API design table IX). Managers only.

    GET    /api/admin/delivery/queue                        orders waiting, oldest first
    GET    /api/admin/delivery/vehicles                     vehicles and their limits
    POST   /api/admin/delivery/trips                        create a trip (see below)
    GET    /api/admin/delivery/trips                        ?status=planned
    GET    /api/admin/delivery/trips/<trip_id>              stops, totals, capacity left, route
    POST   /api/admin/delivery/trips/<trip_id>/orders       {"order_id"}; rechecks both limits
    DELETE /api/admin/delivery/trips/<trip_id>/orders/<order_id>   back to the queue
    POST   /api/admin/delivery/trips/<trip_id>/route        re-plan the route
    POST   /api/admin/delivery/trips/<trip_id>/dispatch     send it to the vehicle
    GET    /api/admin/delivery/exceptions                   orders that cannot be scheduled, and why

Creating a trip, POST /api/admin/delivery/trips:
    {}                                   fill a trip from the queue, oldest order first
    {"order_ids": [4, 7, 9]}             a trip of exactly these orders
    {"vehicle_id": 2, ...}               use this vehicle (default: the first free one)

The order of events follows the design's manager workflow: the capacity
check comes first (10 orders and 200 lb, both at once, read from the
vehicle's own record), then the route is planned, and only a trip that
passed both can be dispatched. The route is re-planned automatically
whenever a trip's orders change, and cannot be changed once dispatched.

Routes use each address's saved coordinates. Addresses are checked with
the mapping service when the customer saves them, so an address that
cannot be found never reaches a trip.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, request

import db
import rules
from common import MANAGER, ApiError, body, current_user, ok, require_int, require_role
from order_status import change_status
from services import mapping
from services import vehicle as vehicle_service

delivery_bp = Blueprint("delivery", __name__)

TRIP_STATUSES = ("planned", "out_for_delivery", "completed")


# =====================================================================
# Reading trips
# =====================================================================

def _vehicle(vehicle_id):
    return db.query_one("SELECT * FROM vehicles WHERE vehicle_id = %s", (vehicle_id,))


def _trip(trip_id, cur=None, lock=False):
    sql = "SELECT * FROM delivery_trips WHERE trip_id = %s" + (" FOR UPDATE" if lock else "")
    if cur is not None:
        cur.execute(sql, (trip_id,))
        row = cur.fetchone()
    else:
        row = db.query_one(sql, (trip_id,))
    if row is None:
        raise ApiError("No such trip", 404, "NOT_FOUND")
    return row


def _stops(trip_id, cur=None):
    sql = (
        "SELECT t.order_id, o.order_number, o.status, o.total_weight_lb, t.stop_sequence, "
        "       t.est_arrival, t.delivered_at, a.street, a.city, a.state, a.zip_code, "
        "       a.latitude, a.longitude, u.full_name AS customer_name "
        "FROM trip_orders t JOIN orders o ON o.order_id = t.order_id "
        "JOIN addresses a ON a.address_id = o.address_id "
        "JOIN users u ON u.user_id = o.user_id "
        "WHERE t.trip_id = %s "
        "ORDER BY t.stop_sequence IS NULL, t.stop_sequence, t.trip_order_id"
    )
    if cur is not None:
        cur.execute(sql, (trip_id,))
        return cur.fetchall()
    return db.query_all(sql, (trip_id,))


def _totals(stops):
    weight = sum((Decimal(s["total_weight_lb"]) for s in stops), Decimal("0.00"))
    return len(stops), weight


def trip_json(trip, stops=None):
    stops = _stops(trip["trip_id"]) if stops is None else stops
    vehicle = _vehicle(trip["vehicle_id"])
    count, weight = _totals(stops)
    route = trip["route_json"]
    if isinstance(route, str):
        route = json.loads(route)
    return {
        "trip_id": trip["trip_id"],
        "status": trip["status"],
        "vehicle": {
            "vehicle_id": vehicle["vehicle_id"],
            "name": vehicle["name"],
            "max_orders": vehicle["max_orders"],
            "max_weight_lb": vehicle["max_weight_lb"],
        },
        "order_count": count,
        "total_weight_lb": weight,
        "remaining_orders": vehicle["max_orders"] - count,
        "remaining_weight_lb": vehicle["max_weight_lb"] - weight,
        "capacity_problem": rules.capacity_problem(
            count, weight, vehicle["max_orders"], vehicle["max_weight_lb"]),
        "route_planned": trip["route_planned_at"] is not None,
        "route": route,
        "stops": [
            {
                "order_id": s["order_id"],
                "order_number": s["order_number"],
                "status": s["status"],
                "customer_name": s["customer_name"],
                "address": f"{s['street']}, {s['city']}, {s['state']} {s['zip_code']}",
                "latitude": s["latitude"],
                "longitude": s["longitude"],
                "weight_lb": s["total_weight_lb"],
                "stop_sequence": s["stop_sequence"],
                "est_arrival": s["est_arrival"],
                "delivered_at": s["delivered_at"],
            }
            for s in stops
        ],
        "created_at": trip["created_at"],
        "started_at": trip["started_at"],
        "completed_at": trip["completed_at"],
        "last_report": trip["last_report"],
        "last_position": (
            {"latitude": trip["last_latitude"], "longitude": trip["last_longitude"],
             "at": trip["last_report_at"]}
            if trip["last_latitude"] is not None else None
        ),
    }


QUEUE_SQL = (
    "SELECT o.order_id, o.order_number, o.total_weight_lb, o.placed_at, o.unscheduled_reason, "
    "       TIMESTAMPDIFF(MINUTE, o.placed_at, NOW()) AS waited_minutes "
    "FROM orders o LEFT JOIN trip_orders t ON t.order_id = o.order_id "
    "WHERE o.status = 'awaiting_delivery' AND t.order_id IS NULL "
    "ORDER BY o.placed_at, o.order_id"
)


def _free_vehicle_ids(cur):
    cur.execute(
        "SELECT v.vehicle_id FROM vehicles v WHERE v.status = 'available' AND NOT EXISTS ("
        "  SELECT 1 FROM delivery_trips d WHERE d.vehicle_id = v.vehicle_id "
        "  AND d.status IN ('planned', 'out_for_delivery')) "
        "ORDER BY v.vehicle_id FOR UPDATE"
    )
    return [r["vehicle_id"] for r in cur.fetchall()]


# =====================================================================
# Route planning
# =====================================================================

def plan_route(cur, trip_id):
    """Order the trip's stops and set every arrival estimate. Returns None
    on success, or the reason it failed (the trip is then left without a
    route, so it cannot be dispatched)."""
    stops = _stops(trip_id, cur)
    if not stops:
        cur.execute("UPDATE delivery_trips SET route_json = NULL, route_planned_at = NULL "
                    "WHERE trip_id = %s", (trip_id,))
        return "The trip has no orders"

    store = mapping.store_location()
    points = [(s["order_id"], mapping.GeoPoint(s["latitude"], s["longitude"])) for s in stops]
    try:
        route = mapping.provider().route(store, points)
    except mapping.MappingError as exc:
        cur.execute("UPDATE delivery_trips SET route_json = NULL, route_planned_at = NULL "
                    "WHERE trip_id = %s", (trip_id,))
        return str(exc)

    leave_at = datetime.now().replace(microsecond=0)
    for sequence, order_id in enumerate(route.stop_order, start=1):
        cur.execute(
            "UPDATE trip_orders SET stop_sequence = %s, est_arrival = %s "
            "WHERE trip_id = %s AND order_id = %s",
            (sequence, leave_at + timedelta(seconds=route.arrival_seconds[order_id]),
             trip_id, order_id),
        )
    route_json = {
        "provider": route.provider,
        "store": {"latitude": str(store.latitude), "longitude": str(store.longitude)},
        "path": route.path,
        "total_minutes": round(route.total_seconds / 60),
    }
    cur.execute(
        "UPDATE delivery_trips SET route_json = %s, route_planned_at = NOW() WHERE trip_id = %s",
        (json.dumps(route_json), trip_id),
    )
    return None


# =====================================================================
# Queue, vehicles, exceptions
# =====================================================================

@delivery_bp.get("/api/admin/delivery/queue")
@require_role(*MANAGER)
def queue():
    return ok(orders=db.query_all(QUEUE_SQL))


@delivery_bp.get("/api/admin/delivery/vehicles")
@require_role(*MANAGER)
def vehicles():
    rows = db.query_all(
        "SELECT v.vehicle_id, v.name, v.max_orders, v.max_weight_lb, v.status, "
        "  (SELECT trip_id FROM delivery_trips d WHERE d.vehicle_id = v.vehicle_id "
        "   AND d.status IN ('planned', 'out_for_delivery') LIMIT 1) AS current_trip_id "
        "FROM vehicles v ORDER BY v.vehicle_id"
    )
    return ok(vehicles=rows)


@delivery_bp.get("/api/admin/delivery/exceptions")
@require_role(*MANAGER)
def exceptions():
    waiting = db.query_all(QUEUE_SQL)
    with db.transaction() as cur:
        no_vehicle_free = not _free_vehicle_ids(cur)
    problems = []
    for order in waiting:
        reason = order["unscheduled_reason"]
        if reason is None and no_vehicle_free:
            reason = "No vehicle is free right now"
        if reason:
            problems.append({**order, "reason": reason})
    return ok(orders=problems)


# =====================================================================
# Trips
# =====================================================================

def _lock_queue(cur):
    cur.execute(QUEUE_SQL + " FOR UPDATE")
    return cur.fetchall()


def _assign(cur, trip_id, order_id, manager_id):
    cur.execute("INSERT INTO trip_orders (trip_id, order_id) VALUES (%s, %s)", (trip_id, order_id))
    cur.execute("UPDATE orders SET unscheduled_reason = NULL WHERE order_id = %s", (order_id,))
    change_status(cur, order_id, "awaiting_delivery", "assigned_to_trip", manager_id, "trip")


@delivery_bp.post("/api/admin/delivery/trips")
@require_role(*MANAGER)
def create_trip():
    data = body()
    manager_id = current_user()["user_id"]
    left_waiting, too_heavy = [], []
    nothing_fits = False

    with db.transaction() as cur:
        free = _free_vehicle_ids(cur)
        if "vehicle_id" in data:
            vehicle_id = require_int(data, "vehicle_id")
            if _vehicle(vehicle_id) is None:
                raise ApiError("No such vehicle", 404, "NOT_FOUND")
            if vehicle_id not in free:
                raise ApiError("That vehicle already has a trip or is not available",
                               409, "VEHICLE_BUSY")
        elif free:
            vehicle_id = free[0]
        else:
            raise ApiError("No vehicle is free right now", 409, "NO_VEHICLE_FREE")
        vehicle = _vehicle(vehicle_id)

        waiting = _lock_queue(cur)
        if "order_ids" in data:
            requested = data["order_ids"]
            if not isinstance(requested, list) or not requested:
                raise ApiError("order_ids must be a non-empty list")
            ids = [require_int({"order_id": x}, "order_id") for x in requested]
            if len(set(ids)) != len(ids):
                raise ApiError("order_ids lists the same order twice")
            by_id = {o["order_id"]: o for o in waiting}
            missing = [i for i in ids if i not in by_id]
            if missing:
                raise ApiError(f"Not waiting for delivery: order {missing[0]}",
                               409, "ORDER_NOT_WAITING", order_ids=missing)
            chosen = [by_id[i] for i in ids]
            count, weight = _totals(chosen)
            problem = rules.capacity_problem(count, weight, vehicle["max_orders"],
                                             vehicle["max_weight_lb"])
            if problem:
                raise ApiError(problem, 409, "CAPACITY_EXCEEDED")
        else:
            chosen, too_heavy = rules.fill_trip(waiting, vehicle["max_orders"],
                                                vehicle["max_weight_lb"])
            for order in too_heavy:
                cur.execute(
                    "UPDATE orders SET unscheduled_reason = %s WHERE order_id = %s",
                    (f"Too heavy for the vehicle: {order['total_weight_lb']} lb, "
                     f"limit {vehicle['max_weight_lb']} lb", order["order_id"]),
                )
            chosen_ids = {o["order_id"] for o in chosen}
            left_waiting = [o["order_number"] for o in waiting
                            if o["order_id"] not in chosen_ids and o not in too_heavy]
            nothing_fits = not chosen

        if not nothing_fits:
            cur.execute("INSERT INTO delivery_trips (vehicle_id, created_by) VALUES (%s, %s)",
                        (vehicle_id, manager_id))
            trip_id = cur.lastrowid
            for order in chosen:
                _assign(cur, trip_id, order["order_id"], manager_id)
            route_error = plan_route(cur, trip_id)

    # Raised after the block so the too-heavy notes above are still saved.
    if nothing_fits:
        raise ApiError("There are no orders in the queue that can go on a trip", 409,
                       "NOTHING_TO_SCHEDULE",
                       too_heavy=[o["order_number"] for o in too_heavy])

    return ok(201, trip=trip_json(_trip(trip_id)), route_error=route_error,
              left_waiting=left_waiting,
              too_heavy=[o["order_number"] for o in too_heavy])


@delivery_bp.get("/api/admin/delivery/trips")
@require_role(*MANAGER)
def list_trips():
    status = request.args.get("status")
    if status and status not in TRIP_STATUSES:
        raise ApiError(f"status must be one of: {', '.join(TRIP_STATUSES)}")
    rows = db.query_all(
        "SELECT * FROM delivery_trips "
        f"{'WHERE status = %s' if status else ''} ORDER BY trip_id DESC",
        (status,) if status else (),
    )
    return ok(trips=[trip_json(r) for r in rows])


@delivery_bp.get("/api/admin/delivery/trips/<int:trip_id>")
@require_role(*MANAGER)
def get_trip(trip_id):
    return ok(trip=trip_json(_trip(trip_id)))


def _require_planned(trip):
    if trip["status"] != "planned":
        raise ApiError("This trip has already been dispatched and can no longer change",
                       409, "TRIP_ALREADY_DISPATCHED")


@delivery_bp.post("/api/admin/delivery/trips/<int:trip_id>/orders")
@require_role(*MANAGER)
def add_order_to_trip(trip_id):
    order_id = require_int(body(), "order_id")
    with db.transaction() as cur:
        trip = _trip(trip_id, cur, lock=True)
        _require_planned(trip)
        waiting = {o["order_id"]: o for o in _lock_queue(cur)}
        if order_id not in waiting:
            raise ApiError("That order is not waiting for delivery", 409, "ORDER_NOT_WAITING")

        vehicle = _vehicle(trip["vehicle_id"])
        count, weight = _totals(_stops(trip_id, cur) + [waiting[order_id]])
        problem = rules.capacity_problem(count, weight, vehicle["max_orders"],
                                         vehicle["max_weight_lb"])
        if problem:
            raise ApiError(problem, 409, "CAPACITY_EXCEEDED")

        _assign(cur, trip_id, order_id, current_user()["user_id"])
        route_error = plan_route(cur, trip_id)
    return ok(trip=trip_json(_trip(trip_id)), route_error=route_error)


@delivery_bp.delete("/api/admin/delivery/trips/<int:trip_id>/orders/<int:order_id>")
@require_role(*MANAGER)
def remove_order_from_trip(trip_id, order_id):
    with db.transaction() as cur:
        trip = _trip(trip_id, cur, lock=True)
        _require_planned(trip)
        cur.execute("DELETE FROM trip_orders WHERE trip_id = %s AND order_id = %s",
                    (trip_id, order_id))
        if cur.rowcount == 0:
            raise ApiError("That order is not on this trip", 404, "NOT_ON_TRIP")
        change_status(cur, order_id, "assigned_to_trip", "awaiting_delivery",
                      current_user()["user_id"], "trip", allow_backward=True)
        route_error = plan_route(cur, trip_id)
    return ok(trip=trip_json(_trip(trip_id)),
              route_error=None if route_error == "The trip has no orders" else route_error)


@delivery_bp.post("/api/admin/delivery/trips/<int:trip_id>/route")
@require_role(*MANAGER)
def replan_route(trip_id):
    with db.transaction() as cur:
        _require_planned(_trip(trip_id, cur, lock=True))
        route_error = plan_route(cur, trip_id)
    if route_error:
        raise ApiError(f"The route could not be planned: {route_error}", 502, "ROUTE_FAILED")
    return ok(trip=trip_json(_trip(trip_id)))


@delivery_bp.post("/api/admin/delivery/trips/<int:trip_id>/dispatch")
@require_role(*MANAGER)
def dispatch(trip_id):
    manager_id = current_user()["user_id"]
    with db.transaction() as cur:
        trip = _trip(trip_id, cur, lock=True)
        _require_planned(trip)
        stops = _stops(trip_id, cur)
        if not stops:
            raise ApiError("The trip has no orders", 409, "TRIP_EMPTY")

        vehicle = _vehicle(trip["vehicle_id"])
        count, weight = _totals(stops)
        problem = rules.capacity_problem(count, weight, vehicle["max_orders"],
                                         vehicle["max_weight_lb"])
        if problem:
            raise ApiError(problem, 409, "CAPACITY_EXCEEDED")
        if trip["route_planned_at"] is None:
            raise ApiError("Plan the route before dispatching", 409, "NO_ROUTE")
        if vehicle["status"] != "available":
            raise ApiError(f"{vehicle['name']} is not available", 409, "VEHICLE_BUSY")

        cur.execute("UPDATE delivery_trips SET status = 'out_for_delivery', started_at = NOW() "
                    "WHERE trip_id = %s", (trip_id,))
        cur.execute("UPDATE vehicles SET status = 'on_trip' WHERE vehicle_id = %s",
                    (vehicle["vehicle_id"],))
        for stop in stops:
            change_status(cur, stop["order_id"], "assigned_to_trip", "out_for_delivery",
                          manager_id, "trip")

        # Last, so a vehicle that refuses the trip rolls all of the above back.
        accepted = vehicle_service.link().send_trip(vehicle, trip_id, [
            {"order_id": s["order_id"], "order_number": s["order_number"],
             "latitude": str(s["latitude"]), "longitude": str(s["longitude"]),
             "est_arrival": s["est_arrival"].isoformat() if s["est_arrival"] else None}
            for s in stops
        ])
        if not accepted:
            raise ApiError(f"{vehicle['name']} did not accept the trip", 502, "VEHICLE_REJECTED")

    return ok(trip=trip_json(_trip(trip_id)))


# =====================================================================
# Completing a stop (called by the vehicle, the simulator, or a manager)
# =====================================================================

def complete_stop(trip_id, order_id, changed_by=None, source="vehicle"):
    """Mark one order on a trip delivered. When it is the trip's last
    undelivered stop, the trip is completed and its vehicle freed.
    Reporting the same stop twice is harmless. Returns the trip's status."""
    with db.transaction() as cur:
        trip = _trip(trip_id, cur, lock=True)
        cur.execute("SELECT delivered_at FROM trip_orders WHERE trip_id = %s AND order_id = %s",
                    (trip_id, order_id))
        stop = cur.fetchone()
        if stop is None:
            raise ApiError("That order is not on this trip", 404, "NOT_ON_TRIP")
        if stop["delivered_at"] is not None:
            return trip["status"]
        if trip["status"] != "out_for_delivery":
            raise ApiError("This trip has not been dispatched", 409, "TRIP_NOT_STARTED")

        change_status(cur, order_id, "out_for_delivery", "delivered", changed_by, source)
        cur.execute("UPDATE trip_orders SET delivered_at = NOW() "
                    "WHERE trip_id = %s AND order_id = %s", (trip_id, order_id))

        cur.execute("SELECT COUNT(*) AS left_to_go FROM trip_orders "
                    "WHERE trip_id = %s AND delivered_at IS NULL", (trip_id,))
        if cur.fetchone()["left_to_go"] == 0:
            cur.execute("UPDATE delivery_trips SET status = 'completed', completed_at = NOW() "
                        "WHERE trip_id = %s", (trip_id,))
            cur.execute("UPDATE vehicles SET status = 'available' WHERE vehicle_id = %s",
                        (trip["vehicle_id"],))
            return "completed"
        return trip["status"]
