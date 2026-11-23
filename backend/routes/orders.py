import json
import os
import re
import secrets

from flask import Blueprint, request
from pymysql.err import IntegrityError

import db
import rules
from common import CUSTOMER, ApiError, body, current_user, ok, require_int, require_role
from routes import cart as cart_routes
from routes.addresses import address_json, owned_address
from services import mapping, payments

orders_bp = Blueprint("orders", __name__)

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ORDER_NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def order_items(order_id):
    rows = db.query_all(
        "SELECT product_id, product_name, quantity, unit_price, unit_weight_lb "
        "FROM order_items WHERE order_id = %s ORDER BY order_item_id",
        (order_id,),
    )
    return [
        {
            "product_id": r["product_id"],
            "name": r["product_name"],
            "quantity": r["quantity"],
            "unit_price": r["unit_price"],
            "unit_weight_lb": r["unit_weight_lb"],
            "line_total": r["unit_price"] * r["quantity"],
        }
        for r in rows
    ]


def status_history(order_id):
    return db.query_all(
        "SELECT h.from_status, h.to_status, h.source, h.changed_at, u.full_name AS changed_by "
        "FROM order_status_history h LEFT JOIN users u ON u.user_id = h.changed_by "
        "WHERE h.order_id = %s ORDER BY h.history_id",
        (order_id,),
    )


def order_summary(row):
    return {
        "order_id": row["order_id"],
        "order_number": row["order_number"],
        "status": row["status"],
        "placed_at": row["placed_at"],
        "delivered_at": row["delivered_at"],
        "subtotal": row["subtotal"],
        "tax": row["tax"],
        "delivery_fee": row["delivery_fee"],
        "total_weight_lb": row["total_weight_lb"],
        "grand_total": row["grand_total"],
    }


def order_detail(row):
    address = db.query_one("SELECT * FROM addresses WHERE address_id = %s", (row["address_id"],))
    payment = db.query_one(
        "SELECT card_last4, status, created_at, gateway_ref FROM payments "
        "WHERE order_id = %s AND status = 'approved' ORDER BY transaction_id DESC LIMIT 1",
        (row["order_id"],),
    )
    if payment:
        payment["method"] = "paypal" if str(payment.pop("gateway_ref") or "").startswith("paypal_") else "card"
    return {
        **order_summary(row),
        "address": address_json(address),
        "items": order_items(row["order_id"]),
        "payment": payment,
    }


def _own_order(order_number):
    row = db.query_one(
        "SELECT * FROM orders WHERE order_number = %s AND user_id = %s",
        (order_number, current_user()["user_id"]),
    )
    if row is None:
        raise ApiError("No such order", 404, "NOT_FOUND")
    return row


def _address_for(user_id, data):
    address_id = require_int(data, "address_id")
    address = owned_address(user_id, address_id)
    if address is None:
        raise ApiError("Please choose one of your saved delivery addresses",
                       422, "INVALID_ADDRESS")
    return address


def _cart_or_error(user_id):
    quantities = cart_routes.quantities(user_id)
    if not quantities:
        raise ApiError("Your cart is empty", 409, "CART_EMPTY")
    return quantities


def _problems(lines):
    return [
        {"product_id": ln["product_id"], "name": ln["name"], "problem": cart_routes.line_problem(ln)}
        for ln in lines
        if cart_routes.line_problem(ln)
    ]


def _raise_if_problems(lines):
    problems = _problems(lines)
    if problems:
        raise ApiError("Some items in your cart can no longer be bought as they are",
                       409, "CART_NEEDS_CHANGES", items=problems)


# GET /api/payments/config: Public: which card gateway is on (fake or stripe), its currency, and whether PayPal is offered.
@orders_bp.get("/api/payments/config")
def payment_config():
    return ok(**payments.public_config())


# POST /api/payments/paypal/order: Creates a PayPal order for the cart total (the server works out the amount).
@orders_bp.post("/api/payments/paypal/order")
def create_paypal_order():
    user = current_user()
    if user is not None and user["role"] != "customer":
        raise ApiError("Staff accounts cannot place orders", 403, "FORBIDDEN")
    paypal = payments.paypal_gateway()
    if paypal is None:
        raise ApiError("PayPal is not available right now", 404, "PAYPAL_UNAVAILABLE")

    lines = cart_routes.cart_lines(_cart_or_error(user["user_id"] if user else None))
    _raise_if_problems(lines)
    totals = rules.price_lines(lines)
    try:
        order_id = paypal.create_order(totals["grand_total"])
    except payments.PaymentGatewayError:
        raise ApiError("We could not reach PayPal. You have not been charged; please try again.",
                       502, "PAYMENT_UNAVAILABLE") from None
    return ok(201, id=order_id, amount=str(totals["grand_total"]))


# POST /api/checkout/preview: Shows the full total with tax for an address; changes nothing.
@orders_bp.post("/api/checkout/preview")
@require_role(*CUSTOMER)
def preview():
    user_id = current_user()["user_id"]
    data = body()
    quantities = _cart_or_error(user_id)
    address = _address_for(user_id, data)

    lines = cart_routes.cart_lines(quantities)
    _raise_if_problems(lines)
    totals = rules.price_lines(lines)
    return ok(
        address=address_json(address),
        items=cart_routes.summary(quantities)["items"],
        **totals,
    )


class _PaymentDeclined(Exception):
    def __init__(self, charge, amount):
        self.charge = charge
        self.amount = amount


def _new_order_number():
    return "OFS-" + "".join(secrets.choice(ORDER_NUMBER_ALPHABET) for _ in range(6))


def _order_by_key(user_id, key):
    return db.query_one(
        "SELECT * FROM orders WHERE user_id = %s AND idempotency_key = %s", (user_id, key))


def _record_payment(user_id, key, amount, status, charge, order_id=None):
    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO payments (order_id, user_id, idempotency_key, amount, status, "
            "gateway_ref, card_last4, failure_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (order_id, user_id, key, amount, status, charge.gateway_ref, charge.card_last4,
             charge.decline_reason),
        )


# POST /api/orders: Places an order: takes the payment, saves the order and removes the stock.
@orders_bp.post("/api/orders")
@require_role(*CUSTOMER)
def place_order():
    user_id = current_user()["user_id"]
    data = body()

    key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    if not isinstance(key, str) or not KEY_PATTERN.match(key):
        raise ApiError("idempotency_key is required: 8 to 64 letters, digits, - or _",
                       code="MISSING_IDEMPOTENCY_KEY")

    earlier = _order_by_key(user_id, key)
    if earlier:
        return ok(200, order=order_detail(earlier), duplicate=True)

    address = _address_for(user_id, data)
    token = data.get("payment_token")
    if not isinstance(token, str) or not token:
        raise ApiError("payment_token is required", code="MISSING_PAYMENT_TOKEN")
    quantities = _cart_or_error(user_id)

    try:
        gateway = payments.gateway_for(token)
    except payments.PaymentMethodUnavailable as unavailable:
        raise ApiError(str(unavailable), 400, "PAYMENT_METHOD_UNAVAILABLE") from None
    charge = None
    try:
        with db.transaction() as cur:
            ids = sorted(quantities)
            cur.execute(
                "SELECT p.product_id, p.name, p.price, p.unit_weight_lb, p.is_listed, "
                "       i.quantity_in_stock AS stock "
                "FROM products p JOIN inventory i ON i.product_id = p.product_id "
                f"WHERE p.product_id IN ({db.placeholders(ids)}) "
                "ORDER BY p.product_id FOR UPDATE",
                tuple(ids),
            )
            lines = [{**r, "quantity": quantities[r["product_id"]]} for r in cur.fetchall()]
            if len(lines) != len(ids):
                raise ApiError("Some items in your cart are no longer sold", 409,
                               "CART_NEEDS_CHANGES")

            cur.execute("SELECT order_id FROM orders WHERE user_id = %s AND idempotency_key = %s",
                        (user_id, key))
            if cur.fetchone():
                raise IntegrityError(1062, "duplicate checkout")

            _raise_if_problems(lines)
            totals = rules.price_lines(lines)

            try:
                charge = gateway.charge(totals["grand_total"], token, idempotency_key=key)
            except payments.PaymentGatewayError:
                raise ApiError("We could not reach the payment service. You have not been "
                               "charged; please try again.", 502, "PAYMENT_UNAVAILABLE") from None
            if not charge.approved:
                raise _PaymentDeclined(charge, totals["grand_total"])

            order_number = _new_order_number()
            cur.execute(
                "INSERT INTO orders (order_number, user_id, address_id, subtotal, tax, "
                "delivery_fee, total_weight_lb, grand_total, idempotency_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (order_number, user_id, address["address_id"], totals["subtotal"], totals["tax"],
                 totals["delivery_fee"], totals["total_weight_lb"], totals["grand_total"], key),
            )
            order_id = cur.lastrowid

            for ln in lines:
                cur.execute(
                    "INSERT INTO order_items (order_id, product_id, product_name, quantity, "
                    "unit_price, unit_weight_lb) VALUES (%s, %s, %s, %s, %s, %s)",
                    (order_id, ln["product_id"], ln["name"], ln["quantity"], ln["price"],
                     ln["unit_weight_lb"]),
                )
                cur.execute(
                    "UPDATE inventory SET quantity_in_stock = quantity_in_stock - %s "
                    "WHERE product_id = %s",
                    (ln["quantity"], ln["product_id"]),
                )
                cur.execute(
                    "INSERT INTO inventory_log (product_id, order_id, change_qty, old_quantity, "
                    "new_quantity, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                    (ln["product_id"], order_id, -ln["quantity"], ln["stock"],
                     ln["stock"] - ln["quantity"], f"Sold on order {order_number}"),
                )

            cur.execute(
                "INSERT INTO payments (order_id, user_id, idempotency_key, amount, status, "
                "gateway_ref, card_last4) VALUES (%s, %s, %s, %s, 'approved', %s, %s)",
                (order_id, user_id, key, totals["grand_total"], charge.gateway_ref,
                 charge.card_last4),
            )
            cur.execute(
                "UPDATE payments SET order_id = %s "
                "WHERE user_id = %s AND idempotency_key = %s AND order_id IS NULL",
                (order_id, user_id, key),
            )
            cur.execute(
                "INSERT INTO order_status_history (order_id, from_status, to_status, "
                "changed_by, source) VALUES (%s, NULL, 'placed', %s, 'checkout')",
                (order_id, user_id),
            )
            cart_routes.clear(cur, user_id)

    except _PaymentDeclined as declined:
        _record_payment(user_id, key, declined.amount, "declined", declined.charge)
        raise ApiError(f"Payment declined: {declined.charge.decline_reason}. "
                       "Your cart has not changed.", 402, "PAYMENT_DECLINED") from None

    except Exception as exc:
        if charge is not None and charge.approved:
            if gateway.refund(charge.gateway_ref):
                _record_payment(user_id, key, totals["grand_total"], "refunded", charge)
            else:
                charge.decline_reason = "Order failed and the automatic refund did not go through"
                _record_payment(user_id, key, totals["grand_total"], "approved", charge)
        if isinstance(exc, IntegrityError):
            twin = _order_by_key(user_id, key)
            if twin:
                return ok(200, order=order_detail(twin), duplicate=True)
        raise

    order = db.query_one("SELECT * FROM orders WHERE order_id = %s", (order_id,))
    return ok(201, order=order_detail(order))


# GET /api/orders: Lists the signed-in customer's orders.
@orders_bp.get("/api/orders")
@require_role(*CUSTOMER)
def my_orders():
    rows = db.query_all(
        "SELECT o.*, (SELECT SUM(quantity) FROM order_items WHERE order_id = o.order_id) "
        "       AS item_count "
        "FROM orders o WHERE o.user_id = %s ORDER BY o.placed_at DESC, o.order_id DESC",
        (current_user()["user_id"],),
    )
    return ok(orders=[{**order_summary(r), "item_count": int(r["item_count"] or 0)} for r in rows])


# GET /api/orders/<order_number>: Shows one of the customer's own orders.
@orders_bp.get("/api/orders/<order_number>")
@require_role(*CUSTOMER)
def my_order(order_number):
    return ok(order=order_detail(_own_order(order_number)))


# Builds the status steps, estimate and map data for one order.
def tracking_payload(order):
    history = status_history(order["order_id"])
    position = rules.ORDER_STATUSES.index(order["status"])
    reached = {h["to_status"]: h["changed_at"] for h in history
               if rules.ORDER_STATUSES.index(h["to_status"]) <= position}
    taken_off_trip = (order["status"] == "awaiting_delivery"
                      and any(h["to_status"] == "assigned_to_trip" for h in history))

    stop = db.query_one(
        "SELECT t.trip_id, t.status AS trip_status, t.route_planned_at, t.route_json, "
        "       t.last_report, t.last_latitude, t.last_longitude, t.last_report_at, "
        "       o.stop_sequence, o.est_arrival, "
        "       a.latitude AS destination_latitude, a.longitude AS destination_longitude "
        "FROM trip_orders o JOIN delivery_trips t ON t.trip_id = o.trip_id "
        "JOIN orders placed ON placed.order_id = o.order_id "
        "JOIN addresses a ON a.address_id = placed.address_id "
        "WHERE o.order_id = %s",
        (order["order_id"],),
    )
    estimate = (stop["est_arrival"]
                if stop and stop["route_planned_at"] and stop["route_json"] else None)

    tracking_map = None
    if stop and stop["route_planned_at"] and stop["route_json"]:
        route = stop["route_json"]
        if isinstance(route, str):
            route = json.loads(route)
        store_values = route.get("store") or {}
        store = mapping.GeoPoint(
            store_values.get("latitude"), store_values.get("longitude"))
        destination = mapping.GeoPoint(
            stop["destination_latitude"], stop["destination_longitude"])
        vehicle = None
        if stop["last_latitude"] is not None and stop["last_longitude"] is not None:
            vehicle = mapping.GeoPoint(stop["last_latitude"], stop["last_longitude"])
        route_origin = vehicle or store
        tracking_map = {
            "preview": False,
            "vehicle_mode": os.environ.get("VEHICLE_LINK", "simulated"),
            "provider": route.get("provider", "unknown"),
            "trip_status": stop["trip_status"],
            "store": {
                "latitude": store.latitude,
                "longitude": store.longitude,
            },
            "destination": {
                "latitude": destination.latitude,
                "longitude": destination.longitude,
            },
            "vehicle_position": (
                {
                    "latitude": vehicle.latitude,
                    "longitude": vehicle.longitude,
                }
                if vehicle else None
            ),
            "last_report": stop["last_report"],
            "last_updated": stop["last_report_at"],
            "directions_url": mapping.directions_url(route_origin, destination),
        }
    elif order["status"] != "delivered":
        address = db.query_one(
            "SELECT latitude, longitude FROM addresses WHERE address_id = %s",
            (order["address_id"],),
        )
        if address:
            store = mapping.store_location()
            tracking_map = {
                "preview": True,
                "provider": None,
                "trip_status": stop["trip_status"] if stop else None,
                "store": {"latitude": store.latitude, "longitude": store.longitude},
                "destination": {
                    "latitude": address["latitude"],
                    "longitude": address["longitude"],
                },
                "vehicle_mode": None,
                "vehicle_position": None,
                "last_report": None,
                "last_updated": None,
                "directions_url": None,
            }

    return {
        "order_number": order["order_number"],
        "status": order["status"],
        "steps": [{"status": s, "reached_at": reached.get(s), "done": rules.ORDER_STATUSES.index(s) <= position}
                  for s in rules.ORDER_STATUSES],
        "notice": ("The store took your order off its planned delivery trip. It is back in the queue and will be "
                   "put on a new trip soon; your arrival estimate will appear then.") if taken_off_trip else None,
        "history": [{"status": h["to_status"], "at": h["changed_at"]} for h in history],
        "estimated_arrival": estimate if order["status"] != "delivered" else None,
        "delivered_at": order["delivered_at"],
        "map": tracking_map,
    }


# GET /api/orders/<order_number>/tracking: Shows the status steps, arrival estimate and map for one order.
@orders_bp.get("/api/orders/<order_number>/tracking")
@require_role(*CUSTOMER)
def tracking(order_number):
    return ok(**tracking_payload(_own_order(order_number)))
