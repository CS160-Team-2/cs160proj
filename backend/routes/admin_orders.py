from datetime import date, timedelta
import re

from flask import Blueprint, request

import db
import rules
from common import MANAGER, STAFF, ApiError, body, current_user, ok, require_role
from order_status import change_status
from manager_queries import page_args, pagination
from routes.orders import order_detail, order_summary, status_history, tracking_payload

admin_orders_bp = Blueprint("admin_orders", __name__)

CONTACT_EMAIL = ("CASE WHEN NOT u.is_active AND u.full_name = 'Deleted customer' "
                 "AND SUBSTRING_INDEX(u.email, '@', -1) = 'deleted.ofs.invalid' THEN NULL "
                 "WHEN u.is_guest THEN u.contact_email ELSE u.email END")

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
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            raise ValueError
        return date.fromisoformat(raw)
    except ValueError:
        raise ApiError(f"{name} must be a date like 2026-10-07") from None


# Finds the orders matching the request's filters, with the paging and counts.
def _find_orders(search_email=True):
    where, params = [], []

    status = request.args.get("status")
    if status:
        if status not in rules.ORDER_STATUSES:
            raise ApiError(f"status must be one of: {', '.join(rules.ORDER_STATUSES)}")

    start, end = _date_arg("from"), _date_arg("to")
    if start and end and start > end:
        raise ApiError("From date must be on or before To date", code="INVALID_DATE_RANGE")
    if start:
        where.append("o.placed_at >= %s")
        params.append(start)
    if end and end != date.max:
        where.append("o.placed_at < %s")
        params.append(end + timedelta(days=1))

    query = request.args.get("q", "").strip()
    if len(query) > 255:
        raise ApiError("Search must be 255 characters or fewer")
    if query:
        escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{escaped}%"
        if search_email:
            where.append(
                "(o.order_number LIKE %s ESCAPE '!' OR u.full_name LIKE %s ESCAPE '!' "
                f"OR ({CONTACT_EMAIL}) LIKE %s ESCAPE '!')"
            )
            params.extend((pattern, pattern, pattern))
        else:
            where.append("(o.order_number LIKE %s ESCAPE '!' OR u.full_name LIKE %s ESCAPE '!')")
            params.extend((pattern, pattern))

    base_where = 'WHERE ' + ' AND '.join(where) if where else ''
    paged = 'page' in request.args or 'per_page' in request.args
    page, size = page_args() if paged else (1, 25)
    metadata = {}
    with db.transaction() as cur:
        if paged:
            cur.execute(
                "SELECT o.status, COUNT(*) AS count FROM orders o "
                "JOIN users u ON u.user_id = o.user_id "
                f"{base_where} GROUP BY o.status", tuple(params))
            counts = dict.fromkeys(rules.ORDER_STATUSES, 0)
            counts.update({r['status']: r['count'] for r in cur.fetchall()})
            total = counts[status] if status else sum(counts.values())
            meta = pagination(total, page, size)
            metadata = {'pagination': meta, 'status_counts': counts}
        if status:
            where.append("o.status = %s")
            params.append(status)
        sql = (
        f"SELECT o.*, u.full_name AS customer_name, {CONTACT_EMAIL} AS customer_email, "
        "       u.is_guest, t.trip_id, "
        "       (SELECT SUM(quantity) FROM order_items WHERE order_id = o.order_id) AS item_count "
        "FROM orders o JOIN users u ON u.user_id = o.user_id "
        "LEFT JOIN trip_orders t ON t.order_id = o.order_id "
        f"{'WHERE ' + ' AND '.join(where) if where else ''} "
        "ORDER BY o.placed_at DESC, o.order_id DESC"
        )
        if paged:
            sql += " LIMIT %s OFFSET %s"
            params.extend((size, (meta['page'] - 1) * size))
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return rows, metadata


# GET /api/admin/orders: Lists orders with filters, counts and paging (manager).
@admin_orders_bp.get("/api/admin/orders")
@require_role(*MANAGER)
def list_orders():
    rows, metadata = _find_orders()
    return ok(orders=[
        {**order_summary(r), "customer_name": r["customer_name"],
         "customer_email": r["customer_email"], "is_guest": bool(r["is_guest"]),
         "item_count": int(r["item_count"] or 0),
         "trip_id": r["trip_id"], "unscheduled_reason": r["unscheduled_reason"]}
        for r in rows
    ], **metadata)


# What an employee may see of an order
def _staff_summary(row):
    keep = ("order_id", "order_number", "status", "placed_at", "delivered_at", "total_weight_lb", "grand_total")
    return {**{key: order_summary(row)[key] for key in keep}, "customer_name": row["customer_name"],
            "item_count": int(row["item_count"] or 0), "trip_id": row["trip_id"],
            "unscheduled_reason": row["unscheduled_reason"]}


# GET /api/staff/orders: Read-only order list for employees and managers
@admin_orders_bp.get("/api/staff/orders")
@require_role(*STAFF)
def staff_list_orders():
    rows, metadata = _find_orders(search_email=False)
    return ok(orders=[_staff_summary(r) for r in rows], **metadata)


# GET /api/staff/orders/<int:order_id>: Read-only detail for employees
@admin_orders_bp.get("/api/staff/orders/<int:order_id>")
@require_role(*STAFF)
def staff_get_order(order_id):
    row = _order(order_id)
    detail = order_detail(row)
    customer = db.query_one("SELECT full_name FROM users WHERE user_id = %s", (row["user_id"],))
    trip = db.query_one(
        "SELECT trip_id, stop_sequence, est_arrival, delivered_at FROM trip_orders WHERE order_id = %s", (order_id,))
    return ok(order={
        **{key: detail[key] for key in ("order_id", "order_number", "status", "placed_at", "delivered_at",
                                        "subtotal", "tax", "delivery_fee", "total_weight_lb", "grand_total")},
        "customer_name": customer["full_name"],
        "items": detail["items"],
        "history": [{"status": h["to_status"], "at": h["changed_at"]} for h in status_history(order_id)],
        "trip": trip,
        "unscheduled_reason": row["unscheduled_reason"],
    })


# GET /api/admin/orders/<int:order_id>
@admin_orders_bp.get("/api/admin/orders/<int:order_id>")
@require_role(*MANAGER)
def get_order(order_id):
    row = _order(order_id)
    customer = db.query_one(
        f"SELECT user_id, full_name, {CONTACT_EMAIL} AS email, phone, is_guest "
        "FROM users u WHERE user_id = %s", (row["user_id"],))
    customer["is_guest"] = bool(customer["is_guest"])
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


# PATCH /api/admin/orders/<int:order_id>/status
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
        from routes.delivery import complete_stop
        stop = db.query_one("SELECT trip_id FROM trip_orders WHERE order_id = %s", (order_id,))
        complete_stop(stop["trip_id"], order_id, changed_by=manager_id, source="staff")
    else:
        with db.transaction() as cur:
            change_status(cur, order_id, current, requested, manager_id, "staff")

    return ok(order=order_summary(_order(order_id)))


# GET /api/admin/orders/<int:order_id>/payments
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


# GET /api/admin/orders/<int:order_id>/tracking: The manager may inspect tracking without impersonating a customer.
@admin_orders_bp.get("/api/admin/orders/<int:order_id>/tracking")
@require_role(*MANAGER)
def order_tracking(order_id):
    return ok(**tracking_payload(_order(order_id)))
