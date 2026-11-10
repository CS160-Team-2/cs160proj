"""M5: persisted payment attempts and current scheduling exceptions.

Scheduling timestamps are explicitly order-placement times, not invented
failure times. Resolved scheduling exceptions are not a historical audit log.
"""
from datetime import date, timedelta

from flask import Blueprint, request

import db
from common import MANAGER, ApiError, ok, require_role
from manager_queries import page_args, pagination
from routes.admin_orders import _date_arg

admin_problems_bp = Blueprint('admin_problems', __name__)

# Explicit fields only: never expose tokens, user placeholders or raw payloads.
PROBLEMS_SQL = """
SELECT CONCAT('payment-', p.transaction_id) AS problem_id,
       CASE WHEN p.status = 'approved' THEN 'payment_review' ELSE p.status END AS kind,
       p.created_at AS occurred_at, 'Payment recorded' AS time_label,
       p.order_id, o.order_number, p.transaction_id, p.gateway_ref,
       p.amount, p.card_last4,
       COALESCE(NULLIF(p.failure_reason, ''),
           CASE WHEN p.status = 'refunded' THEN 'Refund recorded'
                ELSE 'Payment declined; no reason was recorded' END) AS reason
FROM payments p LEFT JOIN orders o ON o.order_id = p.order_id
WHERE p.status IN ('declined', 'refunded')
   OR (p.status = 'approved' AND p.order_id IS NULL AND NULLIF(p.failure_reason, '') IS NOT NULL)
UNION ALL
SELECT CONCAT('schedule-', o.order_id), 'unscheduled', o.placed_at, 'Order placed',
       o.order_id, o.order_number, NULL, NULL, NULL, NULL,
       COALESCE(NULLIF(o.unscheduled_reason, ''), 'No vehicle is free right now')
FROM orders o
WHERE o.status = 'awaiting_delivery'
  AND NOT EXISTS (SELECT 1 FROM trip_orders t WHERE t.order_id = o.order_id)
  AND (NULLIF(o.unscheduled_reason, '') IS NOT NULL OR NOT EXISTS (
      SELECT 1 FROM vehicles v WHERE v.status = 'available'
      AND NOT EXISTS (SELECT 1 FROM delivery_trips d WHERE d.vehicle_id = v.vehicle_id
                      AND d.status IN ('planned', 'out_for_delivery'))))
"""


@admin_problems_bp.get('/api/admin/problems')
@require_role(*MANAGER)
def problems():
    page, size = page_args()
    kind = request.args.get('kind', '')
    if kind not in ('', 'declined', 'refunded', 'payment_review', 'unscheduled'):
        raise ApiError('kind must be declined, refunded, payment_review or unscheduled')
    start, end = _date_arg('from'), _date_arg('to')
    if start and end and start > end:
        raise ApiError('From date must be on or before To date', code='INVALID_DATE_RANGE')
    where, params = [], []
    if kind:
        where.append('kind = %s')
        params.append(kind)
    if start:
        where.append('occurred_at >= %s')
        params.append(start)
    if end and end != date.max:
        where.append('occurred_at < %s')
        params.append(end + timedelta(days=1))
    source = f"FROM ({PROBLEMS_SQL}) problems "
    source += 'WHERE ' + ' AND '.join(where) if where else ''
    with db.transaction() as cur:
        cur.execute('SELECT COUNT(*) AS total ' + source, tuple(params))
        meta = pagination(cur.fetchone()['total'], page, size)
        cur.execute('SELECT * ' + source +
                    ' ORDER BY occurred_at DESC, problem_id DESC LIMIT %s OFFSET %s',
                    (*params, size, (meta['page'] - 1) * size))
        rows = cur.fetchall()
    return ok(problems=rows, pagination=meta)
