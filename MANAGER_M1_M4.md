# Manager workflow: M1-M4

Implemented against the supplied `cs160proj-main (5).zip`. No database migration or new package dependencies are required.

## What is included

| Task | Feature |
| --- | --- |
| M1 | `/manager/staff`: list employee/manager accounts, create staff with an initial password, edit contact details and role, deactivate with confirmation, and reactivate without deleting records |
| M2 | Expand an order at `/manager` to view payment attempts: time, transaction ID, gateway reference, status, amount, last four card digits, and failure reason |
| M3 | From/To date fields, inclusive end dates, Today shortcut, invalid-range validation, and Clear filters |
| M4 | Search by order number, customer name or email, including a guest's real checkout email; combine search/date filters with status chips |

The Staff tab is part of the shared manager navigation and also appears as Staff accounts in the account menu. Customer and employee accounts cannot use the manager page or staff-management API.

## Staff protections

- Deactivation retains the account and history; it is not a permanent delete.
- A manager cannot deactivate themselves or remove their own manager role.
- The backend locks staff records in a consistent order and checks the acting manager again inside the transaction. Concurrent managers cannot remove each other's access and leave no active manager.
- Passwords are hashed by the existing backend. They are never returned by staff list/edit/create responses or displayed in the list.
- The create form clears the initial password after success or cancellation.
- The initial password works immediately. A forced first-login password reset and a manager password-reset action are not added by M1.

## Search and payment behavior

Search and dates are applied with the Apply filters button or Enter. Status counts reflect the resulting search/date set; the chips then select its order status. The list continues refreshing with the applied filters. Failed refreshes keep the last successful list and show an error with a retry button. Earlier requests cannot replace newer filter results.

Search is a literal substring search: `%`, `_`, and `!` are treated as text. Names, order numbers and email searches follow the database's existing case-insensitive collation. SQL values remain parameters.

From and To dates can be used separately or together. To includes the whole selected day. Today uses the browser's local calendar date. A From date later than To is rejected by both frontend and backend.

The repo already linked earlier declined retries to the resulting successful order when they used the same checkout key. This behavior is preserved and tested. A failed checkout that never creates an order has no order number to search for; a global problems/payment audit screen remains M5.

Payment history loads independently from order details. A payment lookup error does not hide the items, address or tracking map. The table shows recorded refund attempts but does not add a refund action (M8).

## API contract

- Existing manager-only staff routes: `GET/POST /api/admin/staff`, `PATCH/DELETE /api/admin/staff/<id>`.
- `DELETE` deactivates. `PATCH` with `is_active: true` reactivates.
- Existing manager order list: `GET /api/admin/orders?q=<search>&from=YYYY-MM-DD&to=YYYY-MM-DD&status=<status>`. Parameters are optional. Invalid dates, reversed ranges, and search strings longer than 255 characters are rejected.
- Existing manager payment list: `GET /api/admin/orders/<id>/payments`. Search for the order number to find and expand its order row.

## Automated verification

Verified on Python 3.12.14 and an isolated MySQL 8.0.46 instance:

- New backend staff and order-filter/payment tests: **43 passed**.
- Complete backend suite: **366 passed**, no failed or skipped tests.
- Complete frontend suite: **116 passed** across 14 files.
- Production frontend build: **passed**.

The disposable verification server used a system tablespace to avoid a per-table database-reset directory race on the container's overlay filesystem. No test-reset workaround or storage setting is included in the application patch. The original failing reset case also passed on the clean run.

Existing non-failing output remains: a React `act(...)` warning in the map tests, and Vite's large-bundle warning. Those are outside the M1-M4 implementation.

Repeat these commands locally with MySQL running and the virtual environment active:

```powershell
python -m pytest backend/test_manager_staff.py backend/test_manager_order_filters.py -v
python -m pytest backend -v
cd frontend
npm run test:run
npm run build
cd ..
```

Tests reset `ofs_test`, not the application database `ofs`. Do not run `schema.sql` simply to install these changes.

## Local walkthrough before the pull request

1. Start your normal MySQL, Flask and Vite services. Open `http://localhost:5173` and sign in with `manager@ofs.test` / `manager-pass-1`.
2. Open Staff using the manager tabs or account menu. Check the seeded staff list and that your own Deactivate button is disabled.
3. Add a test employee, such as `qa-m1@example.test`, with name `QA Clerk` and initial password `temporary-pass-1`. Check that the password form closes and the employee appears.
4. Edit this new employee's name, phone and role. Save and refresh to confirm the change persists. Use test accounts rather than deactivating the team's seeded accounts.
5. Deactivate the new account, cancel once to check the confirmation, then confirm. Check it stays listed as inactive. Reactivate it and check the same account returns to active status.
6. A customer opening `/manager/staff` should be redirected home; an employee should go to inventory. Use separate browser profiles/windows to keep sessions separate.
7. Open Orders and expand an existing order. Check the Payments table alongside the existing items, address, history and map. Payment errors should have their own retry button.
8. To see a decline followed by approval, use the fake payment gateway in a customer checkout: first submit test card `4000 0000 0000 0002`, expiry `12/30`, CVC `123`, name `Test Customer`. On that same checkout page, change the card to `4242 4242 4242 4242` and retry. Do not refresh or restart checkout between attempts. Keep the resulting order number.
9. In the manager window, search that order number and Apply filters. Expand it: Declined and Approved should both appear with transaction details and the decline reason. These are test cards for the local fake/test configuration.
10. Search by customer name/email, use Today, then select a status chip. Check that all criteria work together. Reverse From and To dates and confirm the error. Clear filters and confirm the complete list returns.

After this walkthrough and the local tests pass, commit on `andy/manager-workflow-m1-m4`, open a PR against `main`, and mark M1-M4 complete after the team's merge. M2 also addresses MB2 from the checklist.
