# Low-Level Design: current API tables

Replacement/addendum for the earlier LLD API tables, verified against the
uploaded repository plus the manager completion upgrade on 2026-11-16.
When submitting the combined team document, use these tables to update its
API section. The older PDF/Google Doc is not automatically edited by a Git PR.

All paths below start with `/api`. JSON successes contain `ok: true` and
failures contain `ok: false, error: {code, message}`. Money/weight are decimal
strings; dates/times are ISO strings. Human authorization uses the current
active user's session, checked on every request. No full card numbers, CVCs
or vehicle token hashes appear in order or manager responses.

## Public, account, catalog and checkout routes

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | Public | API/database health |
| POST | `/auth/register` | Public | Create customer account |
| POST | `/auth/login` | Public | Authenticate an active account |
| POST | `/auth/logout` | Public | Clear the current session |
| GET | `/auth/me` | Public | Current account or signed-out state |
| PATCH | `/users/me` | Signed-in account | Update permitted own profile fields |
| DELETE | `/users/me` | Customer | Verify password; refuse unfinished orders; anonymize account while preserving historical orders and addresses |
| GET, POST | `/users/me/addresses` | Customer | List/save own delivery addresses; geocode before saving |
| PATCH, DELETE | `/users/me/addresses/<address_id>` | Customer | Edit/hide own address; preserve paid-order address snapshots |
| GET | `/products` | Public | Catalog search/filter/sort |
| GET | `/products/<product_id>` | Public | One product |
| GET | `/categories` | Public | Catalog categories |
| GET | `/product-images/<filename>` | Public | Serve stored product image |
| GET, DELETE | `/cart` | Visitor/customer | View/empty own cart |
| POST | `/cart/items` | Visitor/customer | Add cart item |
| PATCH, DELETE | `/cart/items/<product_id>` | Visitor/customer | Set quantity/remove item |
| GET | `/checkout/estimate` | Visitor/customer | Cart estimate before final address/payment |
| POST | `/checkout/guest` | Visitor | Validate contact/address and start guest checkout |
| POST | `/checkout/preview` | Customer/guest checkout session | Validate address/cart and return checkout totals |
| GET | `/payments/config` | Public | Safe public payment configuration; no secret keys |
| POST | `/payments/paypal/order` | Customer/guest checkout session | Prepare PayPal checkout using server-computed totals |
| POST | `/orders` | Customer/guest checkout session | Charge and create order atomically with stock updates; idempotent checkout key |
| GET | `/orders` | Customer session | Own order history |
| GET | `/orders/<order_number>` | Owning customer session | Preserved order details |
| GET | `/orders/<order_number>/tracking` | Owning customer session | Status/history and own destination tracking |
| POST | `/orders/lookup` | Public, order number + checkout email | Guest/order tracking lookup without another customer's trip details |

Guest checkout uses the existing customer-role session internally; public
registration cannot create staff. Stored guest email placeholders are not
the contact emails shown to managers. Deleted-customer placeholders are
suppressed from manager email displays; historical delivery addresses remain.

## Employee/manager inventory and product routes

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/inventory` | Employee/manager | Inventory search and filters |
| GET | `/admin/inventory/low-stock` | Employee/manager | Low-stock products |
| PATCH | `/admin/inventory/<product_id>` | Employee/manager | Stock delta/threshold update with audit record |
| GET | `/admin/inventory/<product_id>/changes` | Employee/manager | Stock change history |
| POST | `/admin/products` | Employee/manager | Create catalog product and starting stock |
| PATCH, DELETE | `/admin/products/<product_id>` | Employee/manager | Edit/unlist product; preserve purchased snapshots |
| POST, DELETE | `/admin/products/<product_id>/image` | Employee/manager | Upload/remove product picture |
| POST | `/admin/inventory/manifest/preview` | Manager | Multipart CSV `file`; validate and preview restock, no stock mutation |
| POST | `/admin/inventory/manifest` | Manager | Revalidate/apply entire restock CSV atomically; reject duplicate fingerprint |
| GET | `/staff/delivery/trips` | Employee/manager | Read-only trip geometry/progress; omit customer contact/address/payment data |

The `/admin` prefix alone does not imply manager-only: the inventory/product
routes above intentionally allow employees. Manifest application is manager-only.

## Manager staff, order and problems routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/admin/staff` | List/create employee/manager accounts; never return passwords/hashes |
| PATCH | `/admin/staff/<user_id>` | Edit permitted details/role; reactivate staff |
| DELETE | `/admin/staff/<user_id>` | Soft deactivate; protect self and last active manager |
| GET | `/admin/orders` | Orders with `q`, `from`, `to`, `status`; optional bounded `page`, `per_page` |
| GET | `/admin/orders/<order_id>` | Customer, preserved address/items/totals, status history and assigned trip |
| PATCH | `/admin/orders/<order_id>/status` | Valid manager transitions; actor/time audit; trip-driven changes use delivery routes |
| GET | `/admin/orders/<order_id>/payments` | Every linked payment attempt, including declines/refunds; safe transaction fields |
| GET | `/admin/orders/<order_id>/tracking` | Manager view of that order's tracking |
| GET | `/admin/problems` | Declines, recorded refunds, orphan charges needing review, and current scheduling exceptions |

All routes in this table require an active manager. Order search includes
number, customer name and real checkout email. Dates are inclusive; invalid
ranges return 400. Paged order replies add `pagination` and `status_counts`;
counts cover the entire search/date result, before status selection. Without
page parameters, legacy callers retain the unpaged response.

Problems accepts `kind`, `from`, `to`, `page`, `per_page`. Payment timestamps
are recorded attempt times. Scheduling timestamps are explicitly order
placement times, and resolved scheduling problems are not a permanent audit
history. A failed checkout may have no order link. The view initiates no refund.

## Manager delivery routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/admin/delivery/queue` | Waiting orders, oldest first |
| GET, POST | `/admin/delivery/vehicles` | Safe vehicle list; create simulated robot |
| PATCH | `/admin/delivery/vehicles/<vehicle_id>` | Edit free vehicle; refuse active-trip edits; limits at most 10 orders/200 lb |
| GET | `/admin/delivery/exceptions` | Current scheduling failures/reasons |
| GET, POST | `/admin/delivery/trips` | List/filter trips by status; create selected or automatically filled trip |
| GET | `/admin/delivery/trips/<trip_id>` | Ordered stops, totals/capacity, saved route, current provider/change flag and vehicle report |
| POST | `/admin/delivery/trips/<trip_id>/orders` | Add waiting order; recheck both capacity limits and replan |
| DELETE | `/admin/delivery/trips/<trip_id>/orders/<order_id>` | Remove from planned trip back to queue and replan |
| POST | `/admin/delivery/trips/<trip_id>/route` | Explicit replan; failures preserve the previously saved route/estimates |
| POST | `/admin/delivery/trips/<trip_id>/dispatch` | Validate capacity, vehicle, saved route and provider; hand off and advance statuses |
| POST | `/admin/delivery/trips/<trip_id>/simulation/stops/<order_id>/complete` | Confirmed demo fallback (`confirmed: true`); idempotent, audited and simulated-mode only |

All require an active manager. Trip changes are refused after dispatch.
A provider change returns `ROUTE_PROVIDER_CHANGED` until replan succeeds;
`NO_ROUTE` prevents dispatch without a saved route. Two workers completing
the same stop cannot create duplicate delivery history or release twice.

## Vehicle callbacks

| Method | Path | Access/purpose |
| --- | --- | --- |
| POST | `/fleet/trips/<trip_id>/stops/<order_id>/completed` | Vehicle bearer token for its assigned trip; idempotent stop completion |
| POST | `/fleet/trips/<trip_id>/status` | Assigned vehicle bearer token; validated progress/coordinates; cannot finish with outstanding stops |

A human session never substitutes for a vehicle token. Only its SHA-256
hash is stored. The automatic simulator uses the same transaction-safe stop
completion logic internally, with `simulation` as its audit source.

## Manager UI routes and stop-list exports

`/manager`, `/manager/delivery`, `/manager/staff`, `/manager/problems`,
`/manager/vehicles`, and `/manager/delivery/trips/<trip_id>/manifest` are
manager-only screens. Employee delivery tracking is `/delivery`.

Orders link to `/manager/delivery?trip=<id>#trip-<id>`; trip stops link back
to `/manager?q=<order_number>&open=<order_id>`. A missing trip is explained.
The stop-list page reads the existing authorized trip API, sorts by saved
stop sequence, and supports browser Print/Save as PDF and CSV download.
CSV cells are quoted and leading spreadsheet formula markers are neutralized.
There is no public manifest file endpoint or server-side export storage.
