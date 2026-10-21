"""Checking out without an account.

    POST /api/checkout/guest      {"contact": {...}, "address": {...}}
    GET  /api/checkout/estimate   the cart's full total, with tax
    POST /api/orders/lookup       {"order_number", "email"}; track an order without signing in

A visitor can fill a cart, then check out by giving a name, email,
phone number and delivery address. This route turns those details into
a guest customer, signs the browser in as that guest, and moves the
visitor's cart across, so the page can go straight on to
POST /api/orders exactly as a registered customer does.

A guest has no password and cannot sign in again later; the browser
session is the only way back to their orders. Their real email is kept
in contact_email, and users.email holds a private placeholder, so a
stranger who types a guest's email cannot reach that guest's orders.

If the email already belongs to a registered account, the visitor is
asked to sign in instead.
"""

import re
import uuid

from flask import Blueprint

import db
import rules
from common import ApiError, body, current_user, ok, require_text, user_json
from routes import cart as cart_routes
from routes.addresses import _geocode, _insert, _load, _validated, address_json
from routes.auth import _load_user, _start_session, _valid_email
from routes.orders import order_detail, tracking_payload

guest_bp = Blueprint("guest", __name__)

UNUSABLE_HASH = "!"
PHONE_PATTERN = re.compile(r"^[0-9+()\-.\s]{7,30}$")


def _contact(data):
    contact = data.get("contact")
    if not isinstance(contact, dict):
        raise ApiError("contact is required")
    first = require_text(contact, "first_name", 60)
    last = require_text(contact, "last_name", 60)
    phone = require_text(contact, "phone", 30)
    if not PHONE_PATTERN.match(phone) or sum(c.isdigit() for c in phone) < 7:
        raise ApiError("Please enter a valid phone number", code="INVALID_PHONE")
    return {"full_name": f"{first} {last}", "email": _valid_email(contact), "phone": phone}


@guest_bp.post("/api/checkout/guest")
def start_guest_checkout():
    if current_user() is not None:
        raise ApiError("You are already signed in", 409, "ALREADY_SIGNED_IN")

    data = body()
    contact = _contact(data)
    address_values = _validated(data.get("address") if isinstance(data.get("address"), dict) else {})

    registered = db.query_one(
        "SELECT user_id FROM users WHERE email = %s AND is_guest = FALSE", (contact["email"],))
    if registered:
        raise ApiError("An account with that email already exists. Please sign in to check out.",
                       409, "ACCOUNT_EXISTS")

    point = _geocode(address_values)

    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash, full_name, phone, role, is_guest, contact_email) "
            "VALUES (%s, %s, %s, %s, 'customer', TRUE, %s)",
            (f"guest-{uuid.uuid4().hex}@guest.ofs.invalid", UNUSABLE_HASH,
             contact["full_name"], contact["phone"], contact["email"]),
        )
        user_id = cur.lastrowid
        address_id = _insert(cur, user_id, address_values, point)

    user = _load_user(user_id)
    _start_session(user)
    return ok(201, user=user_json(user), address=address_json(_load(address_id)))


@guest_bp.get("/api/checkout/estimate")
def estimate():
    user = current_user()
    if user is not None and user["role"] != "customer":
        raise ApiError("Staff accounts do not have a shopping cart", 403, "FORBIDDEN")
    quantities = cart_routes.quantities(user["user_id"] if user else None)
    if not quantities:
        raise ApiError("Your cart is empty", 409, "CART_EMPTY")
    lines = cart_routes.cart_lines(quantities)
    return ok(**rules.price_lines(lines))


@guest_bp.post("/api/orders/lookup")
def lookup_order():
    data = body()
    order_number = require_text(data, "order_number", 20).upper()
    email = _valid_email(data)

    order = db.query_one(
        "SELECT o.* FROM orders o JOIN users u ON u.user_id = o.user_id "
        "WHERE o.order_number = %s "
        "  AND LOWER(CASE WHEN u.is_guest THEN u.contact_email ELSE u.email END) = %s",
        (order_number, email),
    )
    if order is None:
        raise ApiError("We could not find an order with that order number and email.",
                       404, "ORDER_NOT_FOUND")
    return ok(order=order_detail(order), tracking=tracking_payload(order))
