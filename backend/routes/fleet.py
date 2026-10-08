"""Vehicle callbacks (API design table X). Called by the delivery
vehicle, not by people.

    POST /api/fleet/trips/<trip_id>/stops/<order_id>/completed    a delivery was made
    POST /api/fleet/trips/<trip_id>/status                        trip progress

The vehicle proves who it is with its own token:

    Authorization: Bearer <vehicle token>

Only the SHA-256 hash of each token is stored (vehicles.api_token_hash).
A vehicle can only report on trips assigned to it.

Progress body: {"status": "en_route" | "at_stop" | "returning" | "completed" | "problem",
                "latitude": "37.33", "longitude": "-121.88"}   (position optional)
"""

import hashlib

from flask import Blueprint, request

import db
from common import ApiError, body, ok, require_decimal
from routes.delivery import _trip, complete_stop

fleet_bp = Blueprint("fleet", __name__)

REPORTS = ("en_route", "at_stop", "returning", "completed", "problem")


def _authenticated_vehicle():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not header[7:].strip():
        raise ApiError("Vehicle token required", 401, "UNAUTHENTICATED")
    token_hash = hashlib.sha256(header[7:].strip().encode()).hexdigest()
    vehicle = db.query_one("SELECT * FROM vehicles WHERE api_token_hash = %s", (token_hash,))
    if vehicle is None:
        raise ApiError("Unknown vehicle token", 401, "UNAUTHENTICATED")
    return vehicle


def _own_trip(trip_id):
    vehicle = _authenticated_vehicle()
    trip = _trip(trip_id)
    if trip["vehicle_id"] != vehicle["vehicle_id"]:
        raise ApiError("This trip is assigned to a different vehicle", 403, "FORBIDDEN")
    return trip


@fleet_bp.post("/api/fleet/trips/<int:trip_id>/stops/<int:order_id>/completed")
def stop_completed(trip_id, order_id):
    _own_trip(trip_id)
    trip_status = complete_stop(trip_id, order_id)
    return ok(trip_id=trip_id, order_id=order_id, trip_status=trip_status)


@fleet_bp.post("/api/fleet/trips/<int:trip_id>/status")
def trip_status(trip_id):
    trip = _own_trip(trip_id)
    data = body()
    report = data.get("status")
    if report not in REPORTS:
        raise ApiError(f"status must be one of: {', '.join(REPORTS)}")
    if trip["status"] == "planned":
        raise ApiError("This trip has not been dispatched", 409, "TRIP_NOT_STARTED")
    if report == "completed" and trip["status"] != "completed":
        raise ApiError("Some stops on this trip have not been reported delivered",
                       409, "STOPS_OUTSTANDING")

    latitude = require_decimal(data, "latitude") if data.get("latitude") is not None else None
    longitude = require_decimal(data, "longitude") if data.get("longitude") is not None else None
    with db.transaction() as cur:
        cur.execute(
            "UPDATE delivery_trips SET last_report = %s, last_latitude = COALESCE(%s, last_latitude), "
            "last_longitude = COALESCE(%s, last_longitude), last_report_at = NOW() "
            "WHERE trip_id = %s",
            (report, latitude, longitude, trip_id),
        )
    return ok(trip_id=trip_id, recorded=report)
