import rules
from common import ApiError


def change_status(cur, order_id, from_status, to_status, changed_by, source,
                  allow_backward=False):
    if not allow_backward and not rules.is_forward_step(from_status, to_status):
        raise ApiError(f"An order cannot go from {from_status} to {to_status}",
                       409, "INVALID_STATUS_CHANGE")

    extra = ", delivered_at = NOW()" if to_status == "delivered" else ""
    cur.execute(
        f"UPDATE orders SET status = %s{extra} WHERE order_id = %s AND status = %s",
        (to_status, order_id, from_status),
    )
    if cur.rowcount != 1:
        raise ApiError("This order changed while you were working on it. Please refresh.",
                       409, "ORDER_CHANGED")
    cur.execute(
        "INSERT INTO order_status_history (order_id, from_status, to_status, changed_by, source) "
        "VALUES (%s, %s, %s, %s, %s)",
        (order_id, from_status, to_status, changed_by, source),
    )
