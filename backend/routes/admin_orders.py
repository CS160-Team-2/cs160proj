"""Order monitor (API design table VII). Managers only.

    GET   /api/admin/orders                        ?status=placed&from=2026-10-01&to=2026-10-07
    GET   /api/admin/orders/<order_id>             full detail for staff
    PATCH /api/admin/orders/<order_id>/status      {"status": "awaiting_delivery"}
    GET   /api/admin/orders/<order_id>/payments    every attempt, including declines

Which status changes a manager makes here, and which happen elsewhere:

    placed -> awaiting_delivery           here: the order is packed and ready
    awaiting_delivery -> assigned_to_trip   by adding it to a trip (delivery endpoints)
    assigned_to_trip -> out_for_delivery    by dispatching the trip
    out_for_delivery -> delivered           normally the vehicle reports it; a manager
                                            can also confirm it here as a fallback

Any request that goes backwards or skips a step is refused.
"""

from datetime import date, timedelta

from flask import Blueprint, request

import db
import rules
from common import MANAGER, ApiError, body, current_user, ok, require_role
from order_status import change_status
from routes.orders import order_detail, order_summary, status_history

admin_orders_bp = Blueprint("admin_orders", __name__)

TRIP_DRIVEN = {
    "assigned_to_trip": "Add the order to a delivery trip instead",
    "out_for_delivery": "Dispatch the order's trip instead",
}


def _order(order_id):
    row = db.query_one("SELECT * FROM orders WHERE order_id = %s", (order_id,))
    if row is None:
        raise ApiError("No such order", 404, "NOT_FOUND")
    return row


def _date_arg(name):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ApiError(f"{name} must be a date like 2026-10-07") from None


@admin_orders_bp.get("/api/admin/orders")
@require_role(*MANAGER)
def list_orders():
    where, params = [], []

    status = request.args.get("status")
    if status:
        if status not in rules.ORDER_STATUSES:
            raise ApiError(f"status must be one of: {', '.join(rules.ORDER_STATUSES)}")
        where.append("o.status = %s")
        params.append(status)

    start, end = _date_arg("from"), _date_arg("to")
    if start:
        where.append("o.placed_at >= %s")
        params.append(start)
    if end:
        where.append("o.placed_at < %s")           # 'to' includes that whole day
        params.append(end + timedelta(days=1))

    rows = db.query_all(
        "SELECT o.*, u.full_name AS customer_name, u.email AS customer_email, t.trip_id, "
        "       (SELECT SUM(quantity) FROM order_items WHERE order_id = o.order_id) AS item_count "
        "FROM orders o JOIN users u ON u.user_id = o.user_id "
        "LEFT JOIN trip_orders t ON t.order_id = o.order_id "
        f"{'WHERE ' + ' AND '.join(where) if where else ''} "
        "ORDER BY o.placed_at DESC, o.order_id DESC",
        tuple(params),
    )
    return ok(orders=[
        {**order_summary(r), "customer_name": r["customer_name"],
         "customer_email": r["customer_email"], "item_count": int(r["item_count"] or 0),
         "trip_id": r["trip_id"], "unscheduled_reason": r["unscheduled_reason"]}
        for r in rows
    ])


@admin_orders_bp.get("/api/admin/orders/<int:order_id>")
@require_role(*MANAGER)
def get_order(order_id):
    row = _order(order_id)
    customer = db.query_one(
        "SELECT user_id, full_name, email, phone FROM users WHERE user_id = %s", (row["user_id"],))
    trip = db.query_one(
        "SELECT trip_id, stop_sequence, est_arrival, delivered_at FROM trip_orders "
        "WHERE order_id = %s", (order_id,))
    return ok(order={
        **order_detail(row),
        "customer": customer,
        "history": status_history(order_id),
        "trip": trip,
        "unscheduled_reason": row["unscheduled_reason"],
        "next_status": rules.next_status(row["status"]),
    })


@admin_orders_bp.patch("/api/admin/orders/<int:order_id>/status")
@require_role(*MANAGER)
def update_status(order_id):
    requested = body().get("status")
    row = _order(order_id)
    current = row["status"]

    if requested not in rules.ORDER_STATUSES:
        raise ApiError(f"status must be one of: {', '.join(rules.ORDER_STATUSES)}")
    if not rules.is_forward_step(current, requested):
        raise ApiError(f"An order cannot go from {current} to {requested}. "
                       f"The next step is {rules.next_status(current) or 'none, it is delivered'}.",
                       409, "INVALID_STATUS_CHANGE")
    if requested in TRIP_DRIVEN:
        raise ApiError(TRIP_DRIVEN[requested], 409, "USE_DELIVERY_ENDPOINTS")

    manager_id = current_user()["user_id"]
    if requested == "delivered":
        # Same path the vehicle uses, so the trip completes when its last stop does.
        from routes.delivery import complete_stop
        stop = db.query_one("SELECT trip_id FROM trip_orders WHERE order_id = %s", (order_id,))
        complete_stop(stop["trip_id"], order_id, changed_by=manager_id, source="staff")
    else:
        with db.transaction() as cur:
            change_status(cur, order_id, current, requested, manager_id, "staff")

    return ok(order=order_summary(_order(order_id)))


@admin_orders_bp.get("/api/admin/orders/<int:order_id>/payments")
@require_role(*MANAGER)
def order_payments(order_id):
    _order(order_id)
    rows = db.query_all(
        "SELECT transaction_id, amount, status, gateway_ref, card_last4, failure_reason, "
        "created_at FROM payments WHERE order_id = %s ORDER BY transaction_id",
        (order_id,),
    )
    return ok(payments=rows)
