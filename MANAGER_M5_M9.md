# Manager workflow: M5-M9

Built against the supplied `cs160proj-main (6).zip`, including M1-M4. Private
environment files, database schema, seed data, dependency versions and lock
files are unchanged. No SQL migration or new dependencies are required.

## Delivered scope

| Task | Delivered behavior |
| --- | --- |
| M5 | Manager Problems tab: declined attempts, recorded refunds, orphan charges with recorded failure reasons, and current scheduling problems; filtering, newest-first ordering, paging, retry, and links to existing orders |
| M6 | Explicit simulated-stop completion in the Delivery board, usable after Flask restarts or timers stop; confirmation, actor/time/source audit, idempotent retries, tracking updates and vehicle release after the last stop |
| M7 | Order list requests one server-filtered page at a time (25 rows by default); Previous/Next and 10/25/50/100 rows; search/date/status combinations; full-result status counts; filtered polling; stale-response protection |
| M8 | Release scope selected by Andy: existing status/trip management with paid-order snapshots preserved. See `MANAGER_ORDER_SCOPE.md`; cancellation and manager-issued refunds remain future proposals |
| M9 | Manager Vehicles tab: capacity, availability, current trip, add simulated vehicle, edit free vehicles, and maintenance/available transitions. Active-trip edits and invalid capacities are refused by the API |

These tasks are ready for local walkthrough and team PR review. They do not
complete the broader T-19 load tests, T-20 security scan, or T-21 browser/device matrix.

## Important behavior

### Problems

Payment attempts remain in the database even if no order was created. Such
rows say so instead of offering a broken order link. A charge whose checkout
failed and whose automatic refund failed is labeled Payment needs review;
staff must check the gateway separately. This page does not issue refunds.

Scheduling exceptions reflect current orders waiting without a trip,
including the existing recorded reason or the absence of an available vehicle.
They disappear after successful assignment. The timestamp is labeled Order
placed: the current schema does not store when a scheduling reason first
occurred. This screen does not invent a historical failure timestamp or retain
resolved scheduling events. A permanent scheduling-event audit log is separate work.

### Recovery

The simulator still uses process-local timers; it does not automatically
resume its animation after a restart. The selected M6 solution is the manual
demo fallback allowed by the backlog. Open Delivery, find an out-for-delivery
simulated trip, and confirm each unfinished stop with Demo: complete.

Each request targets a specific order, so repeating it cannot accidentally
complete the next order. The existing stop-completion transaction records the
manager, timestamp and `simulation_recovery` source. The last stop completes
the trip and frees its vehicle. This is a simulated delivery, not physical
GPS or robot confirmation. Use the fallback when the simulator has stopped;
do not mix manual recovery with an actively running demo animation.

### Pagination

Search, dates, status and row count are sent to the server. Status counts cover
all orders matching the applied search/date filters, not just the visible
page. Filter and row-size changes reset to page one. If results shrink while
polling, the server clamps the requested page to the last valid page. Dates
remain inclusive and Today remains a local calendar day.

Existing callers that omit both pagination parameters retain the legacy
`orders` response. The manager screen always sends bounded page parameters.
The benchmark is a small local comparison, not proof of production load capacity.

### Vehicles

New vehicles are simulated robots. Names must be nonempty and unique among
the current fleet under the database collation. Maximum orders must be an
integer from 1 through 10; maximum weight must be above zero and at most
200 lb, with at most two decimal places. Both limits apply during assignment.

Vehicles on planned or dispatched trips cannot be edited, including changing
their availability. Dispatch sets On trip; completing its final stop frees
the vehicle. Maintenance vehicles cannot receive new trips. There is no
vehicle-delete operation or hardware-token provisioning screen. Internal
tokens/hashes are never returned by manager endpoints.

## API additions and changes

All of these require an active manager session.

| Method | Endpoint | Contract |
| --- | --- | --- |
| GET | `/api/admin/problems` | Optional `kind`, `from`, `to`, `page`, `per_page`; returns `problems` and `pagination` |
| GET | `/api/admin/orders` | Existing filters plus optional `page`/`per_page`; paged replies also return `pagination` and `status_counts` |
| POST | `/api/admin/delivery/trips/<trip_id>/simulation/stops/<order_id>/complete` | Body `{ "confirmed": true }`; simulated mode only; returns updated trip |
| GET | `/api/admin/delivery/vehicles` | Existing safe fleet list, now also used by Vehicles page |
| POST | `/api/admin/delivery/vehicles` | `name`, `max_orders`, `max_weight_lb`, optional `status` (available or maintenance) |
| PATCH | `/api/admin/delivery/vehicles/<vehicle_id>` | Any subset of the above fields, only without an active trip |

`kind`: declined, refunded, payment_review or unscheduled. Pagination defaults
to page 1 and 25 rows, with at most 100 rows per page. Empty sets have page 1
of 1. Unknown kinds, invalid dates, reversed ranges and invalid page numbers
return 400. Role boundaries return 401/403. Active-trip vehicle edits return
409 with `VEHICLE_HAS_TRIP`. Duplicate names return `VEHICLE_NAME_TAKEN`.

## Automated verification

- Complete backend suite: **416 passed**, no failures or skips, against isolated MySQL 8.0.46.
- Complete frontend suite: **145 passed** across 15 files.
- Production frontend build: **passed**.
- New workflow backend cases: **50**, including permissions, payment privacy,
  failed checkout compensation, dates, paging, recovery, and fleet state/capacity checks.
- New UI cases: **29** beyond M1-M4, covering problems, vehicle forms, recovery,
  permissions and pagination. Existing manager tests were adapted for server-side paging.

The new Problems and Vehicles API modules achieved 100% combined line/branch
coverage in this run. Overall backend combined coverage was 88%; this does
not claim all project modules or requirement tests are complete.

Existing non-failing output: the earlier map-test React `act(...)` warning,
and Vite's large-bundle warning. No dependency versions were changed for them.

### M7 local measurement

An isolated test database containing 1,000 orders, same filters, five measured
Flask test-client requests per case after warmup:

| Request | Returned rows | Response bytes | Median time |
| --- | --- | --- | --- |
| Legacy full order list | 1,000 | 360,916 | 18.42 ms |
| First page, 25 rows | 25 | 9,227 | 5.26 ms |

This measures local request handling/serialization with MySQL. It is not a
Locust concurrency test, network/browser timing, or production p95 result.

Chromium browser verification could not start here because workspace policy
refused its local process-singleton socket. No browser or mobile-layout pass
is claimed. Run the following manual walkthrough on your laptop.

## Run tests on your laptop

From the repo root, with your existing virtual environment and MySQL running:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest backend/test_manager_workflow.py -v
python -m pytest backend -q
cd frontend
npm run test:run
npm run build
cd ..
```

Tests reset the separate `ofs_test` database. Do not run `schema.sql` to
install this upgrade: it recreates the application database.

## Local browser walkthrough

1. Start MySQL normally. Start Flask from `backend` using your existing
   environment, and Vite with `npm run dev` from `frontend`. Open the Vite URL.
2. Sign in as `manager@ofs.test` / `manager-pass-1`. Open Problems. Check its
   loading/empty state, filter controls and refresh button. Existing failed
   attempts may already be visible; their absence does not mean the page failed.
3. To create a decline, use a separate browser profile as the seeded customer
   with the local fake payment gateway. Put an in-stock item in the cart and
   submit test card `4000 0000 0000 0002`, expiry `12/30`, CVC `123`, and a name.
   Do not refresh checkout. The manager Problems view should show the decline
   even before an order exists. Retry on the same checkout page with
   `4242 4242 4242 4242`; after approval, the decline should link to that order.
   Open the link and verify the correct order is found and both attempts are
   visible in its Payments table. These cards are for the fake/test configuration.
4. On Orders, try search/date/status together, Today and Clear filters. Choose
   10 rows per page; if more than 10 orders match, use Next and Previous.
   Counts should cover the whole filtered result, not only those 10 rows.
5. Open Vehicles. Add a test robot with at most 10 orders and 200 lb. Edit a
   free robot to smaller limits and Maintenance; check it cannot be selected
   for a new trip. Restore Available. Use test vehicles rather than changing
   limits on a teammate's active demo robot.
6. Prepare two test orders, assign them to a trip and dispatch. Vehicles should
   display its trip and disable Edit. The API must also reject forced edits.
7. For restart recovery, use a simulated trip with unfinished stops. Stop
   Flask and start it again. Refresh Delivery, find the persisted trip and
   click Demo: complete for one pending stop. Cancel once, then confirm.
   Check that only that stop becomes delivered and its history is updated.
   Confirm the remaining stop(s); the trip should complete and its vehicle
   should become available/editable. No database reset is needed.
8. Use separate profiles to sign in as employee and customer. Neither may
   open `/manager/problems` or `/manager/vehicles`, create/edit vehicles, or
   use demo completion. Confirm ordinary customer ordering and employee
   inventory work still operate normally.
9. Check the new screens at desktop, tablet and phone widths. Record any
   layout issues in GitHub Issues. Read `MANAGER_ORDER_SCOPE.md` with the team.

After the tests and walkthrough pass, commit on your feature branch and open
a PR. Mark M5/M6/M7/M9 complete after review/merge and M8 after acceptance of
the recorded scope decision. Do not mark M10/M11 or unrelated test tasks complete.
