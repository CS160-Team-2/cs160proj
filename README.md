# OFS — On-Demand Food Delivery Service

CS 160 Software Engineering · Section 4 · Team 2 · Fall 2026

OFS is a website for a new local organic food retailer chain in downtown San Jose. Customers can browse organic groceries, add them to a shopping cart, pay online, and have the order delivered to their home by a self-driving vehicle. Store employees and managers use a dashboard to manage the inventory and to monitor orders and deliveries.

## Contents

- [Current status](#current-status)
- [Tech stack](#tech-stack)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Optional integrations](#optional-integrations)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [API overview](#api-overview)
- [Deployment](#deployment)
- [Team](#team)

## Current status

### Customer features (working)

- **Browse products** on the home page (featured and most sold) and on the Products page, with filtering by category and price range, and sorting by name or price.
- **Product page** with price, weight, availability and a quantity field.
- **Shopping cart** with quantity changes, removal, total weight and delivery fee. Delivery is free under 20 lb and $10 at 20 lb or more. Visitors can fill a cart without an account.
- **Checkout** with a delivery address, a card form and an order breakdown that includes tax. Customers can check out **signed in** or **as a guest** (name, email, phone and address, no account needed).
- **Payments** through a built-in fake gateway by default, or Stripe in test mode ([see below](#stripe-test-payments)). Declined payments leave the cart untouched.
- **Orders**: signed-in customers see their order history with live status (placed, awaiting delivery, assigned to a trip, out for delivery, delivered) and a delivery map.
- **Guest order tracking** by order number plus the email used at checkout, from the profile menu ("Track orders").
- **Accounts**: register, sign in, sign out, saved delivery addresses.

### Employee and manager features

- **Inventory console** (`/inventory`) for employees and managers: search and filter, adjust stock with a logged reason, low-stock flags, add, edit, unlist and relist products, and upload or remove a **product picture**.
- Staff sign in on the same page as customers and are sent to the console.

### Backend services

The Flask API is complete for: catalog, cart, accounts, addresses, checkout and orders, inventory, order status changes, delivery trips (10 orders and 200 lb limits), route planning, and the vehicle link (simulated).

### Not built yet

- Manager screens for the order monitor, delivery status board and trip planning (the backend routes exist; the frontend pages are in progress).
- Stripe's own secure card field. The checkout form is a stand-in and only accepts Stripe's test card numbers when Stripe is switched on.
- A real self-driving vehicle (a simulator is used) and Apple Pay or PayPal.

## Tech stack

| Part | Technology |
|---|---|
| Frontend | React 18, Vite 5, Tailwind CSS v4, React Router 7, Mapbox GL JS |
| Backend | Python, Flask 3, PyMySQL, Flask-Cors |
| Database | MySQL 8 |
| Payments | Built-in fake gateway, or Stripe (test mode) |
| Maps | Built-in fake provider, or Mapbox / Google Maps |
| Testing | Pytest (backend), Vitest and Testing Library (frontend), GitHub Actions CI |
| Production | Apache 2.4 serves the built frontend and proxies `/api` to Flask |

## Requirements

| Software | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | **Not 3.13**: some packages have no prebuilt wheels for it |
| Node.js | 20 or newer | CI uses Node 24 |
| MySQL Community Server | 8.0 or 8.4 | 8.0.16 or newer is needed for `CHECK` constraints |
| Git | any recent version | |
| MySQL Workbench | 8.0.36 or newer | Optional, for running the schema and browsing data |
| Docker | any recent version | Optional, only for the Docker test database |

Python packages are listed in [`requirements.txt`](requirements.txt) and frontend packages in [`frontend/package.json`](frontend/package.json). Apple Silicon and Windows are both supported. For detailed, step-by-step installation, including Windows, see [SETUP.md](SETUP.md).

## Getting started

These steps assume the prerequisites above are installed and MySQL is running.

### 1. Get the code

```bash
git clone https://github.com/CS160-Team-2/cs160proj.git
cd cs160proj
```

### 2. Create the database

`backend/schema.sql` must be run **once, as the MySQL root user**. It drops and recreates the `ofs` database, creates the `cs160team2` application user, builds the tables, and loads the seed data (39 products with stock and three demo accounts). It is safe to re-run, but it erases everything in `ofs`.

```bash
mysql -u root -p < backend/schema.sql
```

Or open the file in MySQL Workbench and run it as root.

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
| Customer | `customer@ofs.test` | `customer-pass-1` | Shop and My orders |
| Employee | `employee@ofs.test` | `employee-pass-1` | Inventory console |
| Manager | `manager@ofs.test` | `manager-pass-1` | Inventory console |

You can also check out as a guest with no account. Staff accounts can only be created by a manager (`POST /api/admin/staff`); the public sign-up page always creates customers.

### Running it again later

Each time, start two terminals: `source .venv/bin/activate && cd backend && python app.py` and `cd frontend && npm run dev`. MySQL runs as a background service.

After pulling changes, run `npm install` in `frontend/` and `pip install -r requirements.txt` if the dependency files changed. If `schema.sql` changed, run it again (step 2).

## Configuration

### Backend (`backend/.env`, ignored by Git)

| Variable | Default | Purpose |
|---|---|---|
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | `127.0.0.1`, `3306`, `cs160team2`, `team2_password`, `ofs` | Database connection |
| `FLASK_PORT` | `5001` | Port Flask listens on (5000 clashes with macOS AirPlay) |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The only origin allowed to call the API |
| `SECRET_KEY` | development key | Signs the sign-in cookie. Set your own anywhere except your laptop |
| `PAYMENT_GATEWAY` | `fake` | `fake` or `stripe` |
| `STRIPE_SECRET_KEY` | none | A test key (`sk_test_...`), only with `PAYMENT_GATEWAY=stripe` |
| `MAP_PROVIDER` | `fake` | `fake`, `mapbox` or `google` |
| `MAPBOX_ACCESS_TOKEN`, `GOOGLE_MAPS_API_KEY` | none | Server-side map keys |
| `VEHICLE_LINK`, `VEHICLE_SIMULATION_SECONDS` | `simulated`, `20` | The simulated vehicle completes one stop every N seconds after dispatch. `0` means stops are only completed when reported |
| `TAX_RATE` | `0.09375` | Sales tax rate (San Jose) |
| `PRODUCT_IMAGE_DIR` | `backend/uploads/products` | Where uploaded product pictures are saved |

### Frontend (`frontend/.env`, optional, ignored by Git)

| Variable | Purpose |
|---|---|
| `VITE_API_BASE` | Backend address. Defaults to `http://localhost:5001`. Leave it empty when Apache serves both |
| `VITE_MAPBOX_ACCESS_TOKEN` | A Mapbox **public** token (`pk.`) for the interactive delivery map. Never use a secret `sk.` token |

Never commit `.env` files or keys.

## Optional integrations

Everything runs offline with the built-in fakes. Turn these on only when needed, for example for the demo. The full steps are in [SETUP.md](SETUP.md).

### Stripe test payments

1. Get a test **secret** key (`sk_test_...`) from your Stripe dashboard, in test mode.
2. In `backend/.env`, set `PAYMENT_GATEWAY=stripe` and `STRIPE_SECRET_KEY=sk_test_...`, then restart Flask.
3. Check out with a Stripe test card, any future expiry and any 3-digit security code:

| Card number | Result |
|---|---|
| `4242 4242 4242 4242` | Approved |
| `5555 5555 5555 4444` | Approved |
| `4000 0000 0000 0002` | Declined |
| `4000 0000 0000 9995` | Declined, insufficient funds |
| `4000 0000 0000 0069` | Declined, expired card |

A live key (`sk_live_...`) is refused unless `STRIPE_ALLOW_LIVE=1`, so no real money can move by accident.

### Live maps

Set `MAP_PROVIDER=mapbox` with `MAPBOX_ACCESS_TOKEN` in `backend/.env`, and put the same public token in `frontend/.env` as `VITE_MAPBOX_ACCESS_TOKEN`. Restart Flask and Vite. Without a frontend token, order tracking shows a simple offline diagram and a link to Google Maps.

### Product pictures

Employees upload JPEG, PNG or WebP pictures (up to 5 MB) in the inventory console. Files are saved in `backend/uploads/products/` (ignored by Git), and the database stores a short reference in `products.image_key`. The 39 seeded products use pictures bundled in `frontend/src/assets`. Copy `backend/uploads/` along with the database when moving to another server.

## Running the tests

### Backend

```bash
source .venv/bin/activate
cd backend
pytest                  # about 40 seconds, prints a coverage report
```

The tests rebuild a separate `ofs_test` database before every test, so they never touch the data in `ofs`. `schema.sql` already grants the `cs160team2` user access to it.

### Frontend

```bash
cd frontend
npm run test:run        # run once
npm test                # watch mode
npm run coverage        # with a coverage report
```

### Docker test database (optional)

CI runs the backend tests against a MySQL container on port 3307. To use it locally:

```bash
docker compose -f backend/docker/mysql/compose.yaml up -d
docker compose -f backend/docker/mysql/compose.yaml down     # stop it
```

### Continuous integration

`.github/workflows/ci.yml` runs the backend and frontend tests on every pull request and on pushes to `main`.

## Project structure

```
cs160proj/
├── README.md               This file
├── SETUP.md                Detailed environment setup and troubleshooting
├── WALKTHROUGH.md          Guided tour of the system
├── requirements.txt        Python dependencies
├── check-setup.sh          Checks that the tools are installed
├── .github/                CI workflow and the bug report template
├── backend/
│   ├── app.py              Flask app factory; registers every route module
│   ├── db.py               MySQL connection and transaction helpers
│   ├── common.py           Errors, request parsing, sign-in and role checks
│   ├── rules.py            Pricing, weight, delivery fee, tax, order statuses
│   ├── order_status.py     The order status machine and its audit trail
│   ├── schema.sql          Tables, seed data and the database user
│   ├── reset_db.py         Rebuilds a database from schema.sql
│   ├── routes/             catalog, cart, auth, addresses, orders, guest,
│   │                       inventory, product_images, admin_orders,
│   │                       delivery, fleet
│   ├── services/           payments (fake and Stripe), mapping, vehicle
│   ├── docker/mysql/       Docker test database
│   └── test_*.py           Backend tests
├── frontend/
│   ├── src/pages/          Home, Products, Item, Cart, Checkout, Login,
│   │                       Orders, TrackOrder, Inventory
│   ├── src/components/     NavigationBar, StoreItem, DeliveryMap, ...
│   ├── src/context/        StoreContext (products, cart, sign-in state)
│   ├── src/api.js          Every call to the backend goes through here
│   └── src/assets/         Bundled product pictures
└── deploy/                 Apache configuration and publish script
```

## API overview

All paths start with `/api` and return JSON of the form `{"ok": true, ...}` or `{"ok": false, "error": {...}}`.

| Area | Endpoints | Who |
|---|---|---|
| Catalog | `GET /products`, `/products/<id>`, `/categories` | Everyone |
| Cart | `GET /cart`, `POST /cart/items`, `PATCH` and `DELETE /cart/items/<id>`, `DELETE /cart` | Visitors and customers |
| Accounts | `POST /auth/register`, `/auth/login`, `/auth/logout`, `GET /auth/me`, `PATCH /users/me` | Public or signed in |
| Addresses | `GET`, `POST`, `PATCH`, `DELETE /users/me/addresses` | Customers |
| Checkout | `POST /checkout/guest`, `GET /checkout/estimate`, `POST /checkout/preview` | Visitors, customers |
| Orders | `POST /orders`, `GET /orders`, `GET /orders/<n>`, `GET /orders/<n>/tracking` | Customers |
| Guest tracking | `POST /orders/lookup` (order number plus email) | Everyone |
| Inventory | `GET /admin/inventory`, `PATCH /admin/inventory/<id>`, `POST`, `PATCH` and `DELETE /admin/products` | Employees, managers |
| Product pictures | `POST` and `DELETE /admin/products/<id>/image`, `GET /product-images/<file>` | Staff (upload), everyone (view) |
| Orders and delivery | `/admin/orders`, `/admin/delivery/...`, `/fleet/...` | Managers, the vehicle |
| Staff accounts | `/admin/staff` | Managers |

The design behind these routes is in the team's Low-Level Design document.

## Deployment

In production there is one origin: Apache serves the built React files and forwards `/api` to Flask, so no CORS is involved. Build the frontend with an empty API base so it calls the same origin:

```bash
cd frontend
VITE_API_BASE= npm run build
```

Apache's configuration and a publish script are in [`deploy/`](deploy/) with the steps in [`deploy/APACHE.md`](deploy/APACHE.md).

## Contributing

- Work on a branch and open a pull request into `main`. CI runs the backend and frontend tests on every pull request.
- After pulling, run `npm install` and `pip install -r requirements.txt` when the dependency files changed.
- Report defects with the bug report template under `.github/ISSUE_TEMPLATE/`.

## Team

Andy Martin-Valencia, Donna Bui, Yuji Nishi, Sem Verkerk, Srikar Gokanakonda, Thi Lam

San Jose State University · CS 160 Software Engineering
