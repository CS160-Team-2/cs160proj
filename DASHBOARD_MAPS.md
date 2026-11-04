# Delivery maps across the dashboards

## Views and permissions

| Account | Page | Delivery features |
| --- | --- | --- |
| Customer | `/orders`, then open an order | Own destination, route from the latest vehicle position, milestones, arrival estimate and report age |
| Guest | `/track-order` | Same customer view after order-number and checkout-email lookup |
| Employee | `/delivery` | Read-only trip selector, saved route, numbered stops, completion counts and vehicle reports |
| Manager | `/manager/delivery` | Trip map plus the existing queue, capacity checks, create/edit/route/dispatch actions |
| Manager | `/manager`, then expand an order | Order details and that order's tracking map |

The account menu links staff to delivery tracking. Inventory also links to it. Customers never receive other customers' stops or the manager's full trip. The employee API omits customer names, street addresses, payment details and vehicle tokens. Employees cannot perform manager actions.

New endpoints:

- `GET /api/staff/delivery/trips`: employee or manager, read only.
- `GET /api/admin/orders/<order_id>/tracking`: manager only.

## Local configuration

Keep your existing private environment files. Update these settings in `backend/.env`:

```dotenv
MAP_PROVIDER=mapbox
MAPBOX_ACCESS_TOKEN=YOUR_EXISTING_PUBLIC_MAPBOX_TOKEN
PAYMENT_GATEWAY=fake
VEHICLE_LINK=simulated
VEHICLE_SIMULATION_SECONDS=120
```

In `frontend/.env`:

```dotenv
VITE_MAPBOX_ACCESS_TOKEN=YOUR_EXISTING_PUBLIC_MAPBOX_TOKEN
```

Use a public Mapbox token beginning with `pk.` in the frontend. Restart Flask and Vite after changing environment files. This upgrade requires no new dependencies or SQL schema migrations.

## Map behavior

- Staff maps show route geometry already saved by the backend, including each stop in delivery order. They do not make additional Directions calls on each refresh.
- Customer maps request a road route between the store/latest reported vehicle position and that customer's own address. Changed origins are limited to one route lookup per minute for the same destination.
- Markers update on the existing map instance. `Fit route` resets the view; `Follow vehicle` pans to new reports. Polling otherwise preserves zoom and pan.
- Without a usable browser token/WebGL context, an explicitly labeled position diagram appears. If Directions fails, markers remain visible without a false road route.
- Customer/guest tracking refreshes every 15 seconds; staff delivery views refresh every 10 seconds. Old reports and delayed estimates are labeled.
- Dispatch shifts planned arrival estimates to the actual departure time. It does not continuously recalculate live traffic.

## Simulator

When enabled, the simulated robot reports positions along the saved route about every 2 seconds, and completes one stop each `VEHICLE_SIMULATION_SECONDS` seconds. Set `120` for a two-minute stop, leaving time to compare views. Set `0` to disable automatic reports and completion and use fleet callbacks instead.

These are simulated reports, not physical GPS. The UI labels them accordingly. Routes from the offline `fake` provider may not follow roads; choose Mapbox for road routes. The simulator finishes at the last delivery stop, without a return-drive simulation.

Avoid changing backend files or restarting Flask during a demo trip. Timers run inside the Flask process and do not resume after a restart. Use a new trip afterward. If the map provider changed, re-plan an existing planned trip with the manager's `Re-plan route` button before dispatch.

## Verification

From the repository root, with the virtual environment active and MySQL running:

```powershell
python -m pytest backend/test_dashboard_maps.py backend/test_delivery_tracking_map.py backend/test_vehicle_motion.py -v
python -m pytest backend -v
cd frontend
npm run test:run
npm run build
cd ..
```

Tests use the separate `ofs_test` database. Do not rerun `schema.sql` just to apply this patch: it drops and recreates the application database.

New tests cover role restrictions, employee data minimization, manager tracking, estimate rebasing and rollback, GPS validation, simulator movement, marker updates, route coordinates and missing/stale data.

### Checks performed while preparing this patch

- Seven simulator/geometry unit tests passed with the Python standard library.
- Five JavaScript map coordinate/bounds assertions passed.
- All backend Python files passed compilation.
- Full pytest, Vitest, production build and the live account walkthrough still need to run locally. Dependency downloads were blocked in the preparation environment and no MySQL server was available. Earlier project test counts do not verify this patch.

## Walkthrough for all accounts

1. Keep Flask, Vite and MySQL running. Open `http://localhost:5173`.
2. Sign in with `customer@ofs.test` / `customer-pass-1`. Place an order using a real local address. With the fake payment gateway, use card `4242 4242 4242 4242`, expiry `12/30`, CVC `123` and a name. Keep the order number.
3. In a private/incognito window, sign in with `manager@ofs.test` / `manager-pass-1`. Use a different browser profile for an employee if comparing all three together. Tabs in one profile share a login cookie.
4. At `/manager`, mark the order ready. At `/manager/delivery`, select the order and an available vehicle and create a trip. Choose the trip above the map and check its road route and numbered stops.
5. Dispatch. Leave backend files unchanged while the simulator runs. After 10-15 seconds, check the orange marker and latest report on the manager page and the customer's order page.
6. Sign in with `employee@ofs.test` / `employee-pass-1` in a separate browser profile or after the manager check. Open `/delivery` from the account menu. The same trip should appear without trip-edit or dispatch buttons.
7. Pan/zoom, wait for a refresh, and try `Fit route` and `Follow vehicle`. After about two minutes per stop, delivered stops turn gray and the order becomes delivered.
8. Expand the order at `/manager` and inspect its individual tracking view.
9. Place a separate order signed out and test `/track-order` with its order number and checkout email. Assignment and tracking should work the same way.
10. A customer opening `/delivery` should be redirected to their orders. An employee opening `/manager` should be redirected to inventory.

Commit and open the PR after local tests and the walkthrough pass. Never commit private `.env` files.
