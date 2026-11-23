import re

from flask import Blueprint

import db
from common import CUSTOMER, ApiError, body, current_user, ok, require_role, require_text
import rules
from services import mapping

addresses_bp = Blueprint("addresses", __name__)

FIELDS = ("street", "city", "state", "zip_code")


def address_json(row):
    return {
        "address_id": row["address_id"],
        "street": row["street"],
        "city": row["city"],
        "state": row["state"],
        "zip_code": row["zip_code"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
    }


# The customer's own, not-deleted address, or None.
def owned_address(user_id, address_id):
    return db.query_one(
        "SELECT * FROM addresses WHERE address_id = %s AND user_id = %s AND is_deleted = FALSE",
        (address_id, user_id),
    )


def _validated(data):
    values = {
        "street": require_text(data, "street", 200),
        "city": require_text(data, "city", 100),
        "state": require_text(data, "state", 50),
        "zip_code": require_text(data, "zip_code", 10),
    }
    if not re.fullmatch(r"\d{5}(-\d{4})?", values["zip_code"]):
        raise ApiError("zip_code must be five digits, like 95192", code="INVALID_ZIP")
    return values


def _geocode(values):
    try:
        point = mapping.provider().geocode(**values)
    except mapping.MappingError:
        raise ApiError("The mapping service is unavailable, please try again shortly",
                       503, "MAPPING_UNAVAILABLE") from None
    if point is None:
        raise ApiError("We could not find that address on the map. Please check it.",
                       422, "ADDRESS_NOT_FOUND")
    miles = mapping.miles_from_store(point)
    if not rules.is_in_service_area(miles):
        raise ApiError(f"Sorry, we only deliver within {rules.SERVICE_RADIUS_MILES:g} miles of our San Jose store, "
                       f"and that address is about {miles:.0f} miles away.", 422, "OUTSIDE_DELIVERY_AREA")
    return point


def _insert(cur, user_id, values, point):
    cur.execute(
        "INSERT INTO addresses (user_id, street, city, state, zip_code, latitude, longitude) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, *(values[f] for f in FIELDS), point.latitude, point.longitude),
    )
    return cur.lastrowid


def _load(address_id):
    return db.query_one("SELECT * FROM addresses WHERE address_id = %s", (address_id,))


# GET /api/users/me/addresses: Lists the customer's saved addresses.
@addresses_bp.get("/api/users/me/addresses")
@require_role(*CUSTOMER)
def list_addresses():
    rows = db.query_all(
        "SELECT * FROM addresses WHERE user_id = %s AND is_deleted = FALSE ORDER BY address_id",
        (current_user()["user_id"],),
    )
    return ok(addresses=[address_json(r) for r in rows])


# POST /api/users/me/addresses: Saves a new delivery address after checking it on the map.
@addresses_bp.post("/api/users/me/addresses")
@require_role(*CUSTOMER)
def add_address():
    values = _validated(body())
    point = _geocode(values)
    with db.transaction() as cur:
        address_id = _insert(cur, current_user()["user_id"], values, point)
    return ok(201, address=address_json(_load(address_id)))


# PATCH /api/users/me/addresses/<int:address_id>
@addresses_bp.patch("/api/users/me/addresses/<int:address_id>")
@require_role(*CUSTOMER)
def edit_address(address_id):
    user_id = current_user()["user_id"]
    existing = owned_address(user_id, address_id)
    if existing is None:
        raise ApiError("No such address", 404, "NOT_FOUND")

    data = {f: existing[f] for f in FIELDS} | {k: v for k, v in body().items() if k in FIELDS}
    values = _validated(data)
    point = _geocode(values)

    used = db.query_one("SELECT 1 AS used FROM orders WHERE address_id = %s LIMIT 1", (address_id,))
    with db.transaction() as cur:
        if used:
            cur.execute("UPDATE addresses SET is_deleted = TRUE WHERE address_id = %s", (address_id,))
            address_id = _insert(cur, user_id, values, point)
        else:
            cur.execute(
                "UPDATE addresses SET street = %s, city = %s, state = %s, zip_code = %s, "
                "latitude = %s, longitude = %s WHERE address_id = %s",
                (*(values[f] for f in FIELDS), point.latitude, point.longitude, address_id),
            )
    return ok(address=address_json(_load(address_id)))


# DELETE /api/users/me/addresses/<int:address_id>
@addresses_bp.delete("/api/users/me/addresses/<int:address_id>")
@require_role(*CUSTOMER)
def delete_address(address_id):
    if owned_address(current_user()["user_id"], address_id) is None:
        raise ApiError("No such address", 404, "NOT_FOUND")
    with db.transaction() as cur:
        cur.execute("UPDATE addresses SET is_deleted = TRUE WHERE address_id = %s", (address_id,))
    return ok(deleted=address_id)
