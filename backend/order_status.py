"""Moving an order from one status to the next, with its audit trail.

Every status change goes through change_status(), whoever causes it:
checkout, a manager, trip planning, or the vehicle. It writes the new
status and a history row saying who changed it, from what, and when, in
the caller's transaction.

    placed -> awaiting_delivery -> assigned_to_trip -> out_for_delivery -> delivered

Managers and the vehicle can only move an order one step forward (see
rules.is_forward_step). The single exception is trip planning: when a
manager takes an order off a trip that has not left yet, the order goes
back from assigned_to_trip to awaiting_delivery, because it really is
back in the queue. That is passed as allow_backward=True and still
recorded in the history.
"""

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
        # Someone else changed it between our read and this write.
        raise ApiError("This order changed while you were working on it. Please refresh.",
                       409, "ORDER_CHANGED")
    cur.execute(
        "INSERT INTO order_status_history (order_id, from_status, to_status, changed_by, source) "
        "VALUES (%s, %s, %s, %s, %s)",
        (order_id, from_status, to_status, changed_by, source),
    )
