# OFS — On-Demand Food Delivery Service

CS 160 Software Engineering · Section 4 · Team 2 · Fall 2026

OFS is a website for a new local organic food retailer chain in downtown San Jose. Customers browse organic groceries, fill a cart, pay online and have the order delivered to their home by a self-driving vehicle. Store employees and managers use dashboards to manage the inventory, watch orders and send deliveries out.

**Demo video** (install, configure, customize and use): [Watch the how-to video](https://drive.google.com/file/d/150aqm5CosbRt9qLagM1dLJSXJH7WgoFx/view?usp=drive_link)

## Contents

- [What the app does](#what-the-app-does)
- [Tech stack](#tech-stack)
- [Run it with Docker](#run-it-with-docker)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Optional integrations](#optional-integrations)
- [Security](#security)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [API overview](#api-overview)
- [Deployment](#deployment)
- [Updating after a pull](#updating-after-a-pull)
- [Known limits](#known-limits)
- [Team](#team)

## What the app does

### Customers

- **Browse and search** the home page (featured and most sold) and the Products page. Search by name or by **product number** (shown under each product name), filter by category and price, and sort.
- **Cart** with quantity changes, total weight and delivery fee. Delivery is free under 20 lb and $10 at 20 lb or more, and the cart says how far the order is from that line. A visitor's cart is kept for 14 days without an account.
- **Checkout** signed in or **as a guest** (name, email, phone, address). The delivery address is checked on the map: a made-up address is refused, and so is one more than 25 miles from the San Jose store.
- **Payments** by card (a built-in fake gateway, or Stripe in test mode) and **PayPal** (sandbox). Declined payments leave the cart untouched.
- **Orders** (top bar) with live status and a delivery map, and **Track** (top bar) for guests, by order number plus the email used at checkout. If the store takes an order off its planned trip, the order page says so.
- **Accounts**: register, sign in with an optional **Remember me**, saved addresses, edit details, delete the account.
- Clear pages for errors: unknown addresses (404), a sign-in that ends, and the store being unreachable.

### Employees

Sign in on the same page as customers; employees land on `/inventory`.

- **Inventory console**: search; filter by availability and category; change stock by a number with a **required reason**; set each product's low-stock level; see each product's **stock history**; add, edit, unlist and relist products; upload or remove a product picture. Changes show in the shop straight away.
- **Customer orders** (`/staff/orders`): every order with its status, items and totals, read-only and without contact or payment details.
- **Delivery tracking** (`/delivery`): orders waiting for a trip, orders that cannot be scheduled and why, the vehicles, and every trip with its route on a map. Read-only.

### Managers

Managers land on `/manager`.

- **Order monitor**: search, date and status filters, order details, payment attempts, status history and tracking. Mark an order ready for delivery.
- **Delivery board** (`/manager/delivery`): the queue, capacity checks (10 orders and 200 lb per trip), planned trips, route planning, dispatch, and recovery of simulated deliveries after a restart.
- **Trip stop lists**: printable list and CSV export for the driver.
- **Delivery manifests** (Inventory page): upload a supplier's CSV, preview each product's stock now and after, then apply it. Every manifest has an ID and can be applied once. Sample files are in `examples/delivery-manifests/`.
- **Staff accounts**, **Problems** (declined payments, orders that could not be scheduled) and **Vehicles**.
- Managers also have the inventory console. A manager tab bar links all manager pages.

The scope for what a manager may do to an order is in [MANAGER_ORDER_SCOPE.md](MANAGER_ORDER_SCOPE.md): review, mark ready, manage planned trips, dispatch and confirm delivery. There is no cancellation or refund feature. The route tables are in [docs/LLD_API.md](docs/LLD_API.md).

## Tech stack

| Part | Technology |
|---|---|
| Frontend | React 18, Vite 5, Tailwind CSS v4, React Router 7, Mapbox GL JS, Stripe.js and PayPal buttons |
| Backend | Python 3.12, Flask 3, PyMySQL, Flask-Cors, python-dotenv |
| Database | MySQL 8 |
| Web server | Apache 2.4 serves the built frontend and forwards `/api` to Flask |
| Payments | Built-in fake gateway, Stripe (test mode), PayPal (sandbox) |
| Maps | Built-in fake provider, Mapbox or Google Maps |
| Testing | pytest (backend), Vitest and Testing Library (frontend), Playwright (real browser), GitHub Actions CI |
| Packaging | Docker Compose runs the whole app (database, backend, Apache) with one command |

## Run it with Docker

The easiest way to try the whole app, and the way to hand it to another team. It needs only Docker: no Python, Node.js, MySQL or Apache to install, and the demo data loads by itself.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and start it (Windows 10/11 and macOS, Apple Silicon or Intel; on Windows it uses WSL 2, which its installer sets up).
2. From the repository root run:

   ```bash
   docker compose up --build
   ```

   The first time this downloads and builds everything (a few minutes). Later starts take about 20 seconds. Add `-d` to get your terminal back.
3. Open <http://localhost:8088> and sign in with one of these demo accounts, or check out as a guest. The first screen after a clean start is the shop with 39 products.

   | Workflow | Email | Password |
   |---|---|---|
   | Customer | `customer@ofs.test` | `customer-pass-1` |
   | Employee | `employee@ofs.test` | `employee-pass-1` |
   | Manager | `manager@ofs.test` | `manager-pass-1` |

   More about each account is under [Demo accounts](#demo-accounts).

What starts:

| Container | What it is |
|---|---|
| `db` | MySQL 8. On its first start it loads `backend/schema/schema.sql`: the tables, the 39 products, the two vehicles and the three demo accounts |
| `backend` | The Flask API, served by Waitress. Not reachable from your computer directly |
| `web` | Apache 2.4: serves the built site and forwards `/api` to the backend. This is the only address you open (port 8088) |

Everyday commands (run in the repository root):

| Do this | Command |
|---|---|
| Stop, keeping the data | `docker compose stop` (start again with `docker compose start`) |
| Stop and remove the containers, keeping the data | `docker compose down` |
| **Start over with the demo data** | `docker compose down -v` then `docker compose up -d` |
| See what the app is doing | `docker compose logs -f backend` |
| Open a MySQL prompt | `docker compose exec db mysql -ucs160team2 -pteam2_password ofs` |

Your data (orders, new products, uploaded pictures) lives in a Docker volume, so it survives `stop` and `down`, and only `down -v` erases it. Everything works with no keys: card payments and the map use the built-in fakes, and PayPal is simply not offered.

To change a setting (the port, Stripe or PayPal sandbox keys, a Mapbox token), copy `docker.env.example` to `.env` next to `compose.yaml`, edit it and run `docker compose up --build -d`. The Mapbox and Stripe *publishable* keys are built into the site, so a rebuild is needed after changing them. If port 8088 is taken, set `OFS_PORT` (for example `OFS_PORT=8090 docker compose up -d`). The full guide, with troubleshooting, is in [SETUP.md](SETUP.md#quick-start-with-docker).

The Docker images contain the app only, not the tests or your `.env` files. To change the code, use the normal setup below.

## Requirements

| Software | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | **Not 3.13**: some packages have no prebuilt wheels for it |
| Node.js | 20 or newer | CI uses Node 24 |
| MySQL Community Server | 8.0 or 8.4 | 8.0.16 or newer is needed for `CHECK` constraints |
| Git | any recent version | |
| MySQL Workbench | 8.0.36 or newer | Optional, for running the schema and browsing data |
| Docker | any recent version | Needed for [Run it with Docker](#run-it-with-docker); otherwise optional (the Docker test database) |
| Chrome | any recent version | Optional, for the browser tests |

Python packages are listed in [`requirements.txt`](requirements.txt) and frontend packages in [`frontend/package.json`](frontend/package.json). Apple Silicon and Windows are both supported. For step-by-step installation, including Windows, see [SETUP.md](SETUP.md).

## Getting started

This is the setup for working on the code. To just run the app, use [Run it with Docker](#run-it-with-docker). These steps assume the prerequisites above are installed and MySQL is running.

### 1. Get the code

```bash
git clone https://github.com/CS160-Team-2/cs160proj.git
cd cs160proj
```

### 2. Create the database

`backend/schema/schema.sql` must be run **once, as the MySQL root user**. It drops and recreates the `ofs` database, creates the `cs160team2` application user, builds the tables, and loads the seed data (39 products with stock, two vehicles and three demo accounts). It is safe to re-run, but it erases everything in `ofs`.

```bash
mysql -u root -p < backend/schema/schema.sql
```

Or open the file in MySQL Workbench and run it as root. Later, `python backend/reset_db.py` puts the demo data back without needing root.

### 3. Set up and start the backend

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp backend/.env.example backend/.env # Windows: copy backend\.env.example backend\.env
cd backend
python app.py                        # http://localhost:5001
```

The defaults in `.env.example` match what `schema.sql` creates, so no edits are needed to get running. Check that it works at <http://localhost:5001/api/health>.

### 4. Set up and start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Open <http://localhost:5173>. Use `localhost`, not `127.0.0.1`: the backend only allows requests from `http://localhost:5173`. If port 5173 is already in use, Vite quietly picks another port and every request is then blocked, so stop any old dev server first.

### Demo accounts

Created by `schema.sql`, for local testing only.

| Role | Email | Password | Lands on |
|---|---|---|---|
| Customer | `customer@ofs.test` | `customer-pass-1` | The shop; Orders |
| Employee | `employee@ofs.test` | `employee-pass-1` | Inventory console |
| Manager | `manager@ofs.test` | `manager-pass-1` | Manager order monitor |

You can also check out as a guest with no account. Staff accounts are created by a manager (`POST /api/admin/staff`); the public sign-up page always creates customers.

### Running it again later

Each time, start two terminals: `source .venv/bin/activate && cd backend && python app.py` and `cd frontend && npm run dev`. MySQL runs as a background service.

## Configuration

### Backend (`backend/.env`, ignored by Git)

[`backend/.env.example`](backend/.env.example) has every setting with a one-line description.

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | `127.0.0.1`, `3306`, `cs160team2`, `team2_password`, `ofs` | Database connection |
| `FLASK_PORT` | `5001` | Port Flask listens on (5000 clashes with macOS AirPlay) |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The only origin allowed to call the API |
| `SECRET_KEY` | development key | Signs the sign-in cookie. Set your own anywhere except your laptop |
| `SESSION_COOKIE_SECURE` | off | `1` on HTTPS. Flask then refuses to start on the development `SECRET_KEY` |
| `TRUSTED_PROXIES` | `0` | `1` behind Apache, so rate limits see each visitor |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_*` | on | Limits on failed sign-ins and look-ups |
| `CART_SESSION_DAYS` | `14` | Days a guest's cart and a customer's sign-in last after their last visit. Staff sessions end with the browser |
| `PAYMENT_GATEWAY` | `fake` | `fake` or `stripe` |
| `STRIPE_SECRET_KEY`, `STRIPE_CURRENCY`, `STRIPE_ALLOW_LIVE` | none, `usd`, `0` | Stripe test key; live keys are refused unless `STRIPE_ALLOW_LIVE=1` |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | none | PayPal sandbox app keys. Both set means checkout offers PayPal |
| `PAYPAL_ENV`, `PAYPAL_CURRENCY`, `PAYPAL_ENABLED`, `PAYPAL_ALLOW_LIVE` | `sandbox`, `USD`, `1`, `0` | PayPal environment and switches |
| `MAP_PROVIDER` | `fake` | `fake`, `mapbox` or `google` |
| `MAPBOX_ACCESS_TOKEN`, `GOOGLE_MAPS_API_KEY` | none | Server-side map keys |
| `STORE_LATITUDE`, `STORE_LONGITUDE` | San Jose (SJSU) | Where the store is, for routes and the delivery area |
| `SERVICE_RADIUS_MILES` | `25` | Farthest an address may be from the store (straight line) |
| `VEHICLE_LINK`, `VEHICLE_SIMULATION_SECONDS` | `simulated`, `20` | The simulated vehicle completes one stop every N seconds after dispatch. `0` means stops are only completed when reported |
| `TAX_RATE` | `0.09375` | Sales tax rate (San Jose) |
| `PRODUCT_IMAGE_DIR` | `backend/uploads/products` | Only for old pictures that are still files; they are copied into the database when first shown |

### Frontend (`frontend/.env`, optional, ignored by Git)

| Variable | Purpose |
|---|---|
| `VITE_API_BASE` | Backend address. Defaults to `http://localhost:5001`. Leave it empty when Apache serves both |
| `VITE_MAPBOX_ACCESS_TOKEN` | A Mapbox **public** token (`pk.`) for the interactive delivery map. Never use a secret `sk.` token |
| `VITE_STRIPE_PUBLISHABLE_KEY` | A Stripe **publishable** key (`pk_test_...`) for Stripe's own card field. Empty means the built-in test form. Never use a secret `sk_` key |

Never commit `.env` files or keys.

## Optional integrations

Everything runs offline with the built-in fakes. Turn these on only when needed, for example for the demo. The full steps are in [SETUP.md](SETUP.md).

### Stripe test payments

1. Get a test **secret** key (`sk_test_...`) from your Stripe dashboard, in test mode.
2. In `backend/.env`, set `PAYMENT_GATEWAY=stripe` and `STRIPE_SECRET_KEY=sk_test_...`, then restart Flask. For Stripe's own card field, also put the publishable key in `frontend/.env` as `VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...` and restart Vite.
3. Check out with a Stripe test card, any future expiry and any 3-digit security code:

| Card number | Result |
|---|---|
| `4242 4242 4242 4242` | Approved |
| `5555 5555 5555 4444` | Approved |
| `4000 0000 0000 0002` | Declined |
| `4000 0000 0000 9995` | Declined, insufficient funds |
| `4000 0000 0000 0069` | Declined, expired card |

A live key (`sk_live_...`) is refused unless `STRIPE_ALLOW_LIVE=1`, so no real money can move by accident.

### PayPal (sandbox)

Create a sandbox app at developer.paypal.com and put its Client ID and Secret in `backend/.env` as `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`, then restart Flask. Checkout then shows radio buttons: **Credit or debit card** and **PayPal**. The server checks the amount before it captures the payment. A live PayPal account is refused unless `PAYPAL_ALLOW_LIVE=1`. PayPal's sandbox sometimes fails to load its button; reload the page.

### Live maps

Set `MAP_PROVIDER=mapbox` with `MAPBOX_ACCESS_TOKEN` in `backend/.env`, and put the same public token in `frontend/.env` as `VITE_MAPBOX_ACCESS_TOKEN`. Restart Flask and Vite. With a live provider, a made-up address is refused and routes follow real roads. With the fake provider, any address with a house number is accepted. Without a frontend token, order tracking shows a simple offline diagram and a link to Google Maps.

### Product pictures

Employees upload JPEG, PNG or WebP pictures (up to 5 MB) in the inventory console. The picture is saved in the database (table `product_pictures`), so pictures move with every backup and copy of the database. The 39 seeded products use pictures bundled in `frontend/src/assets`.

### Delivery manifests

A manager restocks from a supplier's CSV on the Inventory page. The file needs the columns `manifest_id`, `product_name` and `quantity`; every line carries the same manifest ID, product names must match exactly (capitals and spaces are ignored), and extra columns are ignored. The preview shows each product's stock now and after, lists every problem by line, and saves nothing; Apply saves it all or nothing, and an ID can be applied only once. Try `examples/delivery-manifests/delivery-good.csv` and `delivery-with-problems.csv`.

## Security

Passwords are hashed (8 to 128 characters), database queries are parameterised, the sign-in cookie is HTTP-only and same-site, and account, cart and order answers are never cached. Failed sign-ins, order look-ups that find nothing, and wrong passwords when changing a password or deleting an account are rate-limited. Details and the steps for HTTPS are in [SETUP.md](SETUP.md#security-and-https).

## Running the tests

Where the tests live:

| Folder | What is in it |
|---|---|
| `backend/test/` | Every backend test (pytest), `conftest.py`, and the fake payment, map and vehicle services the tests use |
| `frontend/test/` | Every frontend unit test (Vitest), in the same folders as `frontend/src` (`pages/`, `components/`, `context/`), plus the shared test setup |
| `frontend/browser_test/` | The real-browser tests (Playwright), named `*.e2e.js` |
| `backend/browser_test/` | What the backend side of the browser tests needs (the clean-up script for the order tests) |

### Backend

```bash
source .venv/bin/activate
cd backend
pytest                  # about 3 minutes: 768 tests, with a coverage report
pytest test/test_security.py      # or just one file
```

The tests rebuild a separate `ofs_test` database before every test, so they never touch the data in `ofs`. `schema.sql` already grants the `cs160team2` user access to it.

### Frontend

```bash
cd frontend
npm run test:run        # run once (321 tests)
npm test                # watch mode (tests are in frontend/test)
npm run coverage        # with a coverage report
```

### Browser tests (Playwright)

Real-browser tests live in `frontend/browser_test/`. They start Flask and Vite if those are not already running and use your local `ofs` database. They leave your data as they found it: stock and settings they change are put back, and a test account they create is deleted. A few throwaway guest carts can remain.

```bash
cd frontend
E2E_CHANNEL=chrome npm run e2e      # uses the Chrome you already have installed (59 tests, about 2 minutes)
# or, once: npx playwright install chromium   then: npm run e2e
```

Optional switches:

- `E2E_WEBKIT=1` also runs the tests in WebKit (Safari's engine); install it once with `npx playwright install webkit`.
- `E2E_ALLOW_ORDERS=1` turns on the tests that place real orders with Stripe test cards. They create guests named `e2e-...@example.test`; remove them afterwards with `python backend/browser_test/cleanup_e2e.py`.
- PayPal and Stripe browser tests skip themselves when their keys are not set.

Set `E2E_BACKEND_COMMAND` if your Python path is not `../.venv/bin/python` (for example on Windows). Restart any Flask you already have running first, so the tests use the latest backend code.

### Docker test database (optional)

CI runs the backend tests against a MySQL container on port 3307. To use it locally:

```bash
docker compose -f backend/docker/mysql/compose.yaml up -d
docker compose -f backend/docker/mysql/compose.yaml down     # stop it
```

### Continuous integration

`.github/workflows/ci.yml` runs the backend tests (with coverage), the frontend tests and the frontend build on every pull request and on pushes to `main`. The browser tests are run by hand.

## Project structure

```
cs160proj/
├── README.md               This file
├── SETUP.md                Detailed environment setup and troubleshooting
├── MANAGER_ORDER_SCOPE.md  What a manager may do to an order
├── requirements.txt        Python dependencies
├── check-setup.sh          Checks that the tools are installed
├── Dockerfile              Builds the backend and web images (compose.yaml uses it)
├── compose.yaml            Runs the whole app: database, backend and web
├── docker.env.example      Optional settings for the Docker setup (copy to .env)
├── .dockerignore           Keeps tests, notes and .env files out of the images
├── docker/                 Apache settings for the web container
├── .github/                CI workflow and the bug report template
├── docs/                   LLD_API.md: the current API tables
├── examples/               Sample delivery manifests (CSV)
├── deploy/                 Apache configuration, publish script and guide
├── backend/
│   ├── app.py              Flask app factory; registers every route module
│   ├── db.py               MySQL connection and transaction helpers
│   ├── common.py           Errors, request parsing, sign-in and role checks
│   ├── rules.py            Pricing, weight, delivery fee, tax, order statuses
│   ├── order_status.py     The order status machine and its audit trail
│   ├── manifest.py         Reads and checks a delivery manifest
│   ├── ratelimit.py        Limits on failed sign-ins and look-ups
│   ├── reset_db.py         Rebuilds a database from schema/schema.sql
│   ├── schema/             Every SQL file: schema.sql (tables, seed data, database user),
│   │                       updates/ (changes for an existing database), docker/ (start-up scripts)
│   ├── routes/             auth, addresses, catalog, cart, orders, guest, inventory,
│   │                       product_images, manifests, admin_orders, admin_problems,
│   │                       admin_vehicles, delivery, fleet
│   ├── services/           payments (fake, Stripe, PayPal), mapping, vehicle
│   ├── docker/mysql/       Docker test database (compose.yaml)
│   ├── test/               Backend tests (pytest) and their fake services
│   └── browser_test/       Support for the browser tests (clean-up script)
└── frontend/
    ├── src/pages/          Home, Products, Item, Cart, Checkout, Login, Account, Orders,
    │                       TrackOrder, Inventory, EmployeeOrders, EmployeeDelivery,
    │                       the Manager pages, NotFound
    ├── src/components/     NavigationBar, Footer, StoreItem, DeliveryMap, StockControls, ...
    ├── src/context/        StoreContext (products, cart, sign-in state)
    ├── src/api.js          Every call to the backend goes through here
    ├── src/assets/         Logo, hero picture and bundled product pictures
    ├── test/               Frontend unit tests (Vitest), same folders as src
    └── browser_test/       Real-browser tests (Playwright)
```

## API overview

All paths start with `/api` and return JSON of the form `{"ok": true, ...}` or `{"ok": false, "error": {...}}`. The full tables are in [docs/LLD_API.md](docs/LLD_API.md).

| Area | Endpoints | Who |
|---|---|---|
| Catalog | `GET /products`, `/products/<id>`, `/categories` | Everyone |
| Cart | `GET /cart`, `POST /cart/items`, `PATCH` and `DELETE /cart/items/<id>`, `DELETE /cart` | Visitors and customers |
| Accounts | `POST /auth/register`, `/auth/login`, `/auth/logout`, `GET /auth/me`, `PATCH` and `DELETE /users/me` | Public or signed in |
| Addresses | `GET`, `POST`, `PATCH`, `DELETE /users/me/addresses` | Customers |
| Checkout | `POST /checkout/guest`, `GET /checkout/estimate`, `POST /checkout/preview`, `GET /payments/config`, `POST /payments/paypal/order` | Visitors, customers |
| Orders | `POST /orders`, `GET /orders`, `GET /orders/<n>`, `GET /orders/<n>/tracking` | Customers |
| Guest tracking | `POST /orders/lookup` (order number plus email) | Everyone |
| Inventory | `GET /admin/inventory`, `/admin/inventory/<id>/changes`, `/admin/categories`, `PATCH /admin/inventory/<id>`, `POST`, `PATCH` and `DELETE /admin/products` | Employees, managers |
| Product pictures | `POST` and `DELETE /admin/products/<id>/image`, `GET /product-images/<file>` | Staff (upload), everyone (view) |
| Staff view | `GET /staff/orders`, `/staff/orders/<id>`, `/staff/delivery/trips`, `/staff/delivery/board` (read-only) | Employees, managers |
| Orders and delivery | `/admin/orders`, `/admin/delivery/...` | Managers |
| Delivery manifests | `POST /admin/inventory/manifest/preview`, `POST /admin/inventory/manifest` | Managers |
| Staff accounts | `/admin/staff` | Managers |
| Vehicle | `POST /fleet/trips/<id>/status`, `/fleet/trips/<id>/stops/<order>/completed` | The vehicle |

## Deployment

In production there is one origin: Apache serves the built React files and forwards `/api` to Flask, so no CORS is involved. Build the frontend with an empty API base so it calls the same origin:

```bash
cd frontend
VITE_API_BASE= npm run build
```

Docker does this for you (see [Run it with Docker](#run-it-with-docker)). To install Apache yourself, its configuration and a publish script are in [`deploy/`](deploy/) with the steps in [`deploy/APACHE.md`](deploy/APACHE.md). The setup was checked with Apache 2.4: the site is served, page addresses fall back to the app, `/api` reaches Flask, and sign-in and checkout work through the single address. Behind Apache set `TRUSTED_PROXIES=1`; for HTTPS see [SETUP.md](SETUP.md#security-and-https).

## Updating after a pull

- Run `npm ci` in `frontend/` and `pip install -r requirements.txt` when `package.json` or `requirements.txt` changed.
- If a pull changed the database layout, either rebuild with `python backend/reset_db.py` (erases your local data) or run the matching script in `backend/schema/updates/` once. [SETUP.md](SETUP.md#updating-your-database-after-a-pull) lists the scripts and commands.
- Work on a branch and open a pull request into `main`. Report defects with the template under `.github/ISSUE_TEMPLATE/`.

## Known limits

- The vehicle is a simulator, not a real self-driving vehicle.
- Apple Pay and Google Pay buttons are built but need an HTTPS domain and a supported device, so they have not been tried on a real device.
- Orders and trips cannot be cancelled or refunded: the project documents do not define it (see [MANAGER_ORDER_SCOPE.md](MANAGER_ORDER_SCOPE.md)).
- There is no password reset, and no email or text message is sent to customers.
- The Docker package uses the development data and fake services by default, and its Flask server keeps the rate-limit counts in memory.
- The rate-limit counts are kept in memory and start again when Flask restarts.

## Team

Andy Martin-Valencia, Donna Bui, Yuji Nishi, Sem Verkerk, Srikar Gokanakonda, Thi Lam

San Jose State University · CS 160 Software Engineering
