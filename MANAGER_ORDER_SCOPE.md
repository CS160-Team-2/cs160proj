# M8: manager order-management scope decision

Status: release scope selected by Andy on 2026-11-10 and ready for the team's
pull-request review. No new cancellation, refund, or paid-order editing
behavior is enabled by this decision.

## Why a decision is needed

The supplied project documentation, Architecture F.1, uses “manage/edit the
order” without defining which purchased fields may change. Architecture F.2
and the LLD order monitor specify a five-stage forward lifecycle:

`placed -> awaiting_delivery -> assigned_to_trip -> out_for_delivery -> delivered`

The new backlog explicitly defines M8 as agreeing on cancellation, refunds,
and editing scope, then creating implementation tasks for the agreed scope.
It does not define a cancelled status or a manager-initiated refund workflow.
The existing payment gateway refund method is already used to compensate
failed checkout transactions; that automatic checkout behavior is preserved.

## Selected release decision

For this release, “manage” means reviewing orders/payments/problems, marking
orders ready, managing planned trip membership/routes, dispatching trips,
and confirming delivered stops. Purchased item, price, quantity, tax, fee,
total-weight and delivery-address snapshots remain unchanged after payment.

| Order state | Permitted manager actions |
| --- | --- |
| placed | Review; mark ready for delivery |
| awaiting_delivery | Review; assign to a capacity-approved trip |
| assigned_to_trip | Review; remove from the planned trip back to the queue; replan; dispatch |
| out_for_delivery | Review tracking; confirm a delivery; use clearly labeled simulated-stop recovery for demos |
| delivered | Review the preserved order, history and payment records |

Viewing a `refunded` payment record does not initiate a refund. Recording a
demo delivery does not contact a physical robot. Editing a saved customer
address or catalog product must not rewrite an existing paid order.

## Acceptance criteria for this scope

- Status changes follow the documented lifecycle; only planned-trip removal
  uses the existing explicit return-to-queue operation.
- Every delivery-status change records actor, timestamp and source.
- Customer and employee sessions cannot invoke manager actions.
- No cancellation/refund buttons suggest an unsupported financial action.
- Automated tests preserve paid-order snapshots, transaction records, role
  boundaries, trip capacities and valid transitions.

## If the team instead needs cancellation/refunds/editing

Agree on these follow-up tasks before implementation:

| Proposed follow-up | Decisions and acceptance criteria needed |
| --- | --- |
| M8-A Cancel before dispatch | Which states can cancel; whether packing/assignment prevents cancellation; atomic stock restoration exactly once; trip removal/replanning; historical order visibility |
| M8-B Refund through the gateway | Full/partial policy; reuse/review the existing gateway refund method; idempotency and pending/failure states; reconciliation after timeout; financial audit trail; cancellation/refund consistency |
| M8-C Change a paid order | Editable fields and allowed states; repricing, taxes, fee/weight/capacity changes; additional payment/refund handling; stock and address snapshots; audit history |

## Team decision record

- Decision: use existing controls for this release; preserve paid-order snapshots.
- Confirmed by: Andy Martin-Valencia, in the M8 scope selection.
- Decision date: 2026-11-10.
- Release scope: status changes and planned-trip management as listed above.
- Follow-ups: M8-A, M8-B and M8-C are future proposals, not approved implementation tasks.
- Team review: include this decision in the M5-M9 pull request.

The scope-selection work for M8 is recorded here. Mark the backlog entry
complete after the team accepts this decision during review; it does not
claim that cancellation, manager-issued refunds, or paid-order editing exist.
