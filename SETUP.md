# OFS — Environment Setup

Step-by-step setup for the OFS project, verified for **Windows 10/11 (x86-64)** and **macOS on Apple Silicon (M1–M5)**.

Follow the parts in order. Each ends with a check — if the check fails, stop and look at [Troubleshooting](#troubleshooting) rather than continuing. Allow about 45 minutes the first time, most of it waiting for installers.

---

## Part 0 — What you are installing

| Software | Version | Why |
|---|---|---|
| **Python** | 3.11 or 3.12 | Backend language. **Not 3.13** — see Troubleshooting #9 |
| **Node.js** | 20 or newer (CI uses 24) | Runs Vite and the frontend tests. Tailwind v4 needs Node 20+ |
| **MySQL Community Server** | 8.0 or 8.4 LTS | The database. 8.0.16 or newer is needed for `CHECK` constraints |
| **MySQL Workbench** | 8.0.36 or newer | Managing the database visually |
| **Git** | any recent | Source control |
| **Docker** | any recent | Optional. Only for the Docker test database in 2.4 |

Everything else installs from `requirements.txt` and `package.json`.

> **Apple Silicon:** download the **ARM64 / Apple Silicon** builds, not Intel. They exist for all four and are noticeably faster. If a MySQL Workbench ARM build is not offered for your macOS version, the Intel build runs under Rosetta 2 — macOS will offer to install Rosetta the first time.

---

## Part 1 — Install the prerequisites

### Windows 10 / 11

1. **Python** — [python.org/downloads](https://www.python.org/downloads/), choose **3.12.x**, Windows installer (64-bit).
   - ☑ **Tick "Add python.exe to PATH"** on the first screen. This is the single most common setup mistake.
2. **Node.js** — [nodejs.org](https://nodejs.org/), the **LTS** Windows Installer (.msi).
3. **MySQL** — [dev.mysql.com/downloads/installer](https://dev.mysql.com/downloads/installer/), *MySQL Installer for Windows*.
   - Choose setup type **Developer Default** (this installs Server + Workbench together).
   - On *Authentication Method*, keep the default **Strong Password Encryption**.
   - Set a root password and **write it down**.
   - On *Windows Service*, keep "Start the MySQL Server at System Startup" ticked.
4. **Git** — [git-scm.com/download/win](https://git-scm.com/download/win), defaults are fine.

**Check** — open **PowerShell** and run:

```powershell
python --version      # Python 3.12.x
node --version        # v20 or newer
npm --version
mysql --version
git --version
```

### macOS (Apple Silicon)

1. **Python** — [python.org/downloads/macos](https://www.python.org/downloads/macos/), **3.12.x**, *macOS 64-bit universal2 installer*.
2. **Node.js** — [nodejs.org](https://nodejs.org/), **LTS**, *macOS Installer (.pkg) — ARM64*.
3. **MySQL Community Server** — [dev.mysql.com/downloads/mysql](https://dev.mysql.com/downloads/mysql/), *macOS ARM, 64-bit DMG Archive*.
   - Keep **Use Strong Password Encryption**.
   - Set a root password and **write it down**.
   - After installing, open **System Settings → MySQL** and click **Start MySQL Server**. Tick *Start MySQL when your computer starts up*.
4. **MySQL Workbench** — [dev.mysql.com/downloads/workbench](https://dev.mysql.com/downloads/workbench/), macOS ARM if offered.
5. **Git** — already present if you have Xcode Command Line Tools; otherwise `xcode-select --install`.

**Check** — open **Terminal** and run:

```bash
python3 --version     # Python 3.12.x
node --version        # v20 or newer
npm --version
git --version
/usr/local/mysql/bin/mysql --version
```

### Get the code (both platforms)

```bash
git clone https://github.com/CS160-Team-2/cs160proj.git
cd cs160proj
```

Every path in the rest of this guide is relative to this `cs160proj` folder (the repository root).

---

## Part 2 — Set up the database in MySQL Workbench

The same on both platforms.

**2.1 Open Workbench and connect as root**

- Launch MySQL Workbench.
- Under *MySQL Connections* you should see **Local instance** (Windows) or **localhost** (macOS). Click it.
- If no connection exists, click the **+**, then:
  - *Connection Name:* `Local MySQL`
  - *Hostname:* `127.0.0.1`  ·  *Port:* `3306`  ·  *Username:* `root`
  - Click **Test Connection**, enter your root password, tick *Save password in vault*.
- Enter the root password when prompted.

**2.2 Run the setup script**

- **File → Open SQL Script…**
- Choose `backend/schema.sql` from the repository.
- Click the **⚡ lightning-bolt** button (*Execute all*), or press **Ctrl+Shift+Enter** / **⌘⇧Enter**.

Prefer the command line? From the repository root, as root:

```bash
mysql -u root -p < backend/schema.sql
```

On macOS the `mysql` program is at `/usr/local/mysql/bin/mysql` if it is not on your PATH.

**2.3 Check the result**

The *Output* panel at the bottom should show green ticks and no red errors. The last results grids should show:

| check_name | result |
|---|---|
| Products loaded: | 39 |
| Users loaded: | 3 |
| MySQL version: | 8.0.x or 8.4.x |

In the left *Navigator* panel, click the **refresh icon** beside SCHEMAS — `ofs` now appears, with its tables (`products`, `inventory`, `users`, `addresses`, `carts`, `orders`, `payments`, `delivery_trips` and more).

**What the script did:** created the `ofs` database, created a user `cs160team2` with password `team2_password` that can use `ofs` and the test database `ofs_test`, built all the tables, and loaded the seed data: 39 products with stock, and three demo accounts (see [Part 5](#part-5--verify-the-whole-system)). Everyone on the team runs the same script, so the same `.env` works on all six machines — nobody needs to share a personal root password.

> ⚠️ Re-running `schema.sql` **drops and recreates** the `ofs` database. Everything in it is erased: orders, accounts you registered, and products you added or edited. Run it again only when you want a clean start, or when the schema changed in a pull (Troubleshooting #14).

**2.4 Docker MySQL Test Database**

This Docker database is for testing. It runs separately from your local MySQL database, so the test data will not affect your local database.

Start the database from the project root:

```bash
docker compose -f backend/docker/mysql/compose.yaml up -d
```

Check if it is running:

```bash
docker compose -f backend/docker/mysql/compose.yaml ps
```

Run the backend tests against it. Activate the venv first, wait until the status shows `(healthy)`, then run:

```bash
cd backend
MYSQL_PORT=3307 pytest -q
```

`MYSQL_PORT=3307` points the tests at the Docker database instead of your local MySQL on 3306. pytest creates and drops its own `ofs_test` database on every run

Stop the database when you are done:

```bash
docker compose -f backend/docker/mysql/compose.yaml down
```

The test database includes six products with different weights to test the 20 lb delivery limit and the 200 lb vehicle capacity

To reset the test database and reload the schema and test data, run:

```bash
docker compose -f backend/docker/mysql/compose.yaml down -v
docker compose -f backend/docker/mysql/compose.yaml up -d
```

**Note:** `down -v` deletes the Docker test database data only. Your local MySQL database is not affected

---

## Part 3 — Set up the backend

Run these from the repository root. The virtual environment lives in the root `.venv` folder.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # see Troubleshooting #2 if blocked

python -m pip install --upgrade pip
pip install -r requirements.txt

copy backend\.env.example backend\.env
cd backend
```

### macOS (Terminal)

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

cp backend/.env.example backend/.env
cd backend
```

Your prompt should now start with `(.venv)`. **The virtual environment must be active every time you work on the backend** — if you open a new terminal, activate it again (`source ../.venv/bin/activate` from `backend/`).

The `.env` defaults match what `schema.sql` created, so no edits are needed unless you changed the user or password. [Configuration](#configuration-reference) lists every setting.

**Check 1 — the tests pass:**

```bash
pytest -q
```

Every test should pass (about 40 seconds). The tests use their own `ofs_test` database, which they rebuild before each test, so they never touch the data in `ofs`. They need MySQL running and `schema.sql` run once.

**Check 2 — the API runs and reaches MySQL:**

```bash
python app.py
```

You should see `Running on http://127.0.0.1:5001`. Leave it running and open a **second terminal**:

```bash
curl http://localhost:5001/api/health
curl http://localhost:5001/api/products
```

The first should return `"ok": true`, `"database": "up"` and your MySQL version. The second lists 39 products, each with `price` and `unit_weight_lb` as **strings** such as `"6.49"` and `"3.00"`. Money and weight are decimal strings on purpose, because the 20 lb delivery rule cannot be trusted with floating-point numbers. If they come back as plain numbers, stop and ask the team.

> On Windows, `curl` in PowerShell is an alias for `Invoke-WebRequest` and formats output differently. Use `curl.exe http://localhost:5001/api/health`, or just open the URL in a browser.

---

## Part 4 — Set up the frontend

Open a **third terminal** (leave Flask running in the second).

```bash
cd frontend
npm install
npm run dev
```

Vite prints `Local: http://localhost:5173/`. Open it, using `localhost` and not `127.0.0.1` (Troubleshooting #6).

Do **not** run `npm install` with `sudo` on macOS. If you get permission errors, see Troubleshooting #7.

---

## Part 5 — Verify the whole system

With Flask (terminal 1) and Vite (terminal 2) running, open `http://localhost:5173`.

### Demo accounts

Created by `schema.sql`, for local testing only.

| Role | Email | Password | After signing in |
|---|---|---|---|
| Customer | `customer@ofs.test` | `customer-pass-1` | Back to the shop; **My orders** in the profile menu |
| Employee | `employee@ofs.test` | `employee-pass-1` | The inventory console at `/inventory` |
| Manager | `manager@ofs.test` | `manager-pass-1` | The inventory console at `/inventory` |

Everyone signs in on the same page (`/login`) and the role decides where they land. The public sign-up page only ever creates customers; staff accounts are created by a manager through the API.

### Check the customer path

1. **Browse.** The home page shows featured and most sold products with pictures. The Products page filters by category and price, searches by name, and sorts. Peaches and raspberries show **Unavailable**.
2. **Add to cart.** Open a product, set a quantity and press *Add to cart*. The cart count in the header goes up. This works without signing in.
3. **Check the 20 lb delivery rule.** Add **6** bags of apples (3.00 lb each) and **1** bunch of bananas (2.00 lb). The cart must show:

   ```
   Total weight   20.00 lb
   Delivery       $10.00        ← not Free
   ```

   Exactly 20.00 lb is charged. If it shows Free, the threshold uses `<=` where it should use `<`. With **5** bags of apples and 1 bunch of bananas (17.00 lb) delivery is Free.
4. **Check out as a guest.** Press checkout without signing in. Enter a name, email, phone and a delivery address (for example `1 Washington Sq`, `San Jose`, `CA`, `95192`), then pay with card `4242 4242 4242 4242`, any future expiry and any 3-digit code. You land on **Orders** with an order number and status.
5. **Track a guest order later.** Open the profile menu, choose **Track orders**, and enter the order number plus the email you used.
6. **Check out signed in.** Sign in as the demo customer, add something, and check out again. The saved name and address are filled in, and the order appears under **My orders**.
7. **Declined card.** Pay with `4000 0000 0000 0002`. You stay on checkout with an error, and the cart is unchanged.

### Check the staff path

1. Sign out, then sign in as `employee@ofs.test`. You land on the inventory console.
2. Search for a product, then change its stock with a number such as `10` or `-3`. Stock cannot go below zero.
3. Press **Add product** and fill in name, price and weight (weight is required). Choose a picture (JPEG, PNG or WebP, up to 5 MB) to upload one. A product without a picture shows a grey placeholder in the shop.
4. Open the shop and check the new product and its picture appear. Unlisting a product hides it.

Where product pictures live: see [Product pictures](#product-pictures).

---

## Product pictures

Employees upload product pictures in the inventory console. The picture file is saved on the server in `backend/uploads/products/`, and the database stores only a short reference (`upload:<random name>.jpg`) in `products.image_key`. The 39 seeded products keep the pictures bundled in `frontend/src/assets`.

- `backend/uploads/` is ignored by Git, so uploaded pictures are **not** shared through the repository. Each machine has its own.
- To store pictures somewhere else, set `PRODUCT_IMAGE_DIR` in `backend/.env`.
- When moving to another server, copy the `uploads` folder along with the database.
- The server accepts only real JPEG, PNG and WebP files up to 5 MB.

---

## Optional: Turn on Stripe test payments

You do not need this to run or test OFS. By default checkout uses a built-in fake payment service that works offline, and the automated tests always use it. Turn on Stripe only when you want payments to go through Stripe's test system and show up in a Stripe dashboard, for example for the demo.

**Test mode only.** A Stripe test key never moves real money. OFS refuses a live key (one starting `sk_live_`) unless you deliberately set `STRIPE_ALLOW_LIVE=1`, which nobody on this project should do.

### 1. Get a test key

Either make your own free account (recommended, so your test payments are only in your dashboard), or ask the team for the shared test key in a private message.

1. Sign up at [stripe.com](https://stripe.com). Test mode needs no business or bank details.
2. In the dashboard, make sure **Test mode** is switched on.
3. Go to **Developers → API keys** and copy the **Secret key**. It starts with `sk_test_`.

### 2. Put it in `backend/.env`

```
PAYMENT_GATEWAY=stripe
STRIPE_SECRET_KEY=sk_test_...your key...
```

Then restart Flask. Nothing else changes, and no extra package is needed.

**Never commit the key or paste it into a public channel, an issue, or a pull request.** `.env` is already in `.gitignore`. Do not put it in GitHub secrets either: those are only visible to GitHub's automated checks, which do not need it, and never reach your laptop or the demo server. The demo server gets the key in its own `backend/.env`.

### 3. Try it

Check out in the shop with any future expiry date, any 3 digit security code, and one of these card numbers:

| Card number | What happens |
|---|---|
| `4242 4242 4242 4242` | Approved (Visa) |
| `5555 5555 5555 4444` | Approved (Mastercard) |
| `4000 0000 0000 0002` | Declined: card declined |
| `4000 0000 0000 9995` | Declined: insufficient funds |
| `4000 0000 0000 0069` | Declined: card expired |

The payment, or the declined attempt, appears in the Stripe dashboard under **Payments**. Only these test numbers work with Stripe for now. Any other number is turned down as an invalid card, because the checkout page does not yet use Stripe's own card field.

### If something goes wrong

- **Checkout fails with a server error, and the Flask terminal mentions `STRIPE_SECRET_KEY`:** the key is missing from `.env`, or it is a live key. Flask only checks the key at the first checkout, not when it starts.
- **Every checkout says it could not reach the payment service:** the key is wrong or was replaced in the dashboard. Copy it again. If that is not it, check your internet connection.
- **A key leaked:** go to **Developers → API keys** in the Stripe dashboard and roll (replace) it. Because it is a test key, no real money was at risk.

To go back to the offline fake, set `PAYMENT_GATEWAY=fake` and restart Flask.

---

## Optional: Turn on live mapping

OFS uses the deterministic fake mapping provider by default, so automated tests
and development do not require an account. A live provider adds real geocoding,
road routing, ETAs, and an interactive customer street map.

### Card-free Mapbox setup

Create a Mapbox demo account using **Start without a card**, verify the email,
and copy the provided public token. It begins with `pk.`.

Put the token in the server-only `backend/.env` so checkout and trip planning
use Mapbox:

```dotenv
MAP_PROVIDER=mapbox
MAPBOX_ACCESS_TOKEN=pk.your_public_token
```

Create `frontend/.env` from `frontend/.env.example` and put the same public
token there so React can load Mapbox street tiles and the customer-specific
road route:

```dotenv
VITE_MAPBOX_ACCESS_TOKEN=pk.your_public_token
```

Vite deliberately exposes variables beginning with `VITE_` to the browser, so
use only a Mapbox **public** `pk.` token here, never a secret `sk.` token. Both
`.env` files are ignored by Git. Restart Flask and Vite after editing them.

### Google server-side alternative

In a Google Cloud project with billing enabled, enable **Geocoding API** and
**Routes API**, restrict an API key to those APIs, and put it only in
`backend/.env`:

```dotenv
MAP_PROVIDER=google
GOOGLE_MAPS_API_KEY=your_key_here
```

The Google key stays on the Flask server. The optional interactive browser map
still uses a Mapbox public token. To return to offline routing, set
`MAP_PROVIDER=fake` and restart Flask.

### Verify the integration

Save a delivery address, create a delivery trip as a manager, and open the
customer's order tracking page. With the frontend Mapbox token configured, the
page displays streets, zoom controls, the road-following delivery route, and
store/customer markers. A vehicle marker appears after the vehicle reports its
first latitude and longitude. Without a frontend token, the page keeps a simple
offline diagram and its key-free **Open route in Google Maps** link.

Automated tests mock every Mapbox and Google network boundary, so the test suite
never consumes quota or needs a real token.

---

## Running it again later

Two terminals, every time (a third for `pytest`, `curl` and git):

| Terminal | Windows | macOS |
|---|---|---|
| 1 — Flask | `.\.venv\Scripts\Activate.ps1`<br>`cd backend`<br>`python app.py` | `source .venv/bin/activate`<br>`cd backend`<br>`python app.py` |
| 2 — Vite | `cd frontend`<br>`npm run dev` | `cd frontend`<br>`npm run dev` |

Run them from the repository root. MySQL runs as a background service and starts with your computer, so you do not start it by hand.

**After pulling new code**, run `npm install` in `frontend/` and `pip install -r requirements.txt` (venv active) if `package.json` or `requirements.txt` changed. If `backend/schema.sql` changed, run it again as in Part 2.

## Configuration reference

Backend settings go in `backend/.env`; frontend settings in `frontend/.env`. Both are ignored by Git. Never commit a key.

| Setting | Default | Purpose |
|---|---|---|
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | `127.0.0.1`, `3306`, `cs160team2`, `team2_password`, `ofs` | Database connection |
| `FLASK_PORT` | `5001` | Port Flask listens on |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The only address allowed to call the API |
| `SECRET_KEY` | development key | Signs the sign-in cookie. Set your own on any shared server |
| `PAYMENT_GATEWAY` | `fake` | `fake` or `stripe` |
| `STRIPE_SECRET_KEY` | none | A `sk_test_` key, used when the gateway is `stripe` |
| `MAP_PROVIDER` | `fake` | `fake`, `mapbox` or `google` |
| `MAPBOX_ACCESS_TOKEN`, `GOOGLE_MAPS_API_KEY` | none | Server-side map keys |
| `VEHICLE_LINK`, `VEHICLE_SIMULATION_SECONDS` | `simulated`, `20` | The simulated vehicle completes one stop every N seconds after dispatch. `0` means stops are only completed when reported |
| `TAX_RATE` | `0.09375` | Sales tax rate |
| `PRODUCT_IMAGE_DIR` | `backend/uploads/products` | Where uploaded pictures are saved |
| `VITE_API_BASE` (frontend) | `http://localhost:5001` | Backend address. Empty means the same server, as in the Apache deployment |
| `VITE_MAPBOX_ACCESS_TOKEN` (frontend) | none | A Mapbox **public** `pk.` token for the interactive delivery map |

---

## Troubleshooting

**1. macOS: "Address already in use" on port 5000**
Port 5000 is used by **AirPlay Receiver** on macOS Monterey and later. OFS uses 5001 for that reason, so this usually means an older copy of the app or a different program is set to use 5000. If you must free 5000: *System Settings → General → AirDrop & Handoff → AirPlay Receiver: Off*.

**2. Windows: "running scripts is disabled on this system"**
PowerShell blocks the venv activation script by default. Run this in the same window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

It applies to that window only and resets when you close it.

**3. `cryptography is required for sha256_password or caching_sha2_password`**
MySQL 8 uses an authentication plugin PyMySQL cannot speak on its own. `cryptography` is in `requirements.txt` for exactly this reason — you have a stale install. Re-run `pip install -r requirements.txt` with the venv active.

**4. `Access denied for user 'cs160team2'@'localhost'`**
`schema.sql` did not finish, or was run against a different MySQL instance. Re-run it as root (Part 2) and confirm the check shows 39 products. Check that `MYSQL_USER` and `MYSQL_PASSWORD` in `backend/.env` match the script. If `backend/.env` does not exist yet, copy it from `.env.example`: without it, Flask tries to connect with an empty password.

**5. `Can't connect to MySQL server on '127.0.0.1'`**
The server is not running.
*Windows:* `services.msc` → find `MySQL80` → Start.
*macOS:* System Settings → MySQL → Start MySQL Server.

**6. Browser console: `blocked by CORS policy`**
Either Flask is not running (check terminal 1), or the origin does not match. `FRONTEND_ORIGIN` in `.env` must be exactly `http://localhost:5173` — not `127.0.0.1:5173`, which the browser treats as a different origin even though it is the same machine.

**7. macOS: `EACCES` permission errors from `npm install`**
Do not use `sudo`. Fix ownership instead:

```bash
sudo chown -R $(whoami) ~/.npm
```

**8. `npm run dev` fails on the Tailwind plugin**
Your Node is too old — Tailwind v4 needs Node 20+. Check with `node --version` and install the current LTS.

**9. `pip install` tries to build from source and fails**
Almost always Python 3.13. Some packages here have no 3.13 wheels yet, so pip falls back to compiling, which needs Visual C++ Build Tools on Windows. Install Python 3.12 and recreate the venv: delete the `.venv` folder and redo Part 3.

**10. macOS: `error: externally-managed-environment`**
You are installing outside a virtual environment. Make sure the prompt shows `(.venv)` — run the activation step from Part 3 again.

**11. Port 5173 already in use**
Another Vite server is running, probably from an earlier session. Do not accept the next free port: the backend only allows requests from `http://localhost:5173`, so the app on another port shows "Cannot reach the store right now. Is the backend running?" even though Flask is fine. Find the old terminal and stop it with Ctrl+C, or run `lsof -nP -iTCP:5173 -sTCP:LISTEN` (macOS) to find and `kill` it, then start Vite again.

**12. Everything installed but `python` is not found (Windows)**
The "Add python.exe to PATH" box was missed during install. Re-run the installer, choose *Modify*, and tick it. Or use `py` instead of `python`.

**13. After a pull: `Cannot find package 'vitest'`, `mapbox-gl` missing, or a blank page**
New frontend packages were added. Run `npm install` in `frontend/`, then start Vite again.

**14. After a pull: `Unknown column 'is_guest'` or another database error**
The database layout changed. Run `backend/schema.sql` again as root (Part 2). This resets `ofs` to the seed data.

**15. The shop says "Cannot reach the store right now"**
Flask is not running, or Vite is not on port 5173 (see #6 and #11). Check <http://localhost:5001/api/health> in a browser.

**16. An uploaded product picture does not show**
Check that Flask is running and that the file exists in `backend/uploads/products/`. Pictures are saved on each machine, not in Git, so a picture uploaded on one laptop does not appear on another.

**17. Checkout with Stripe fails or every card is refused**
See *If something goes wrong* under Stripe test payments above. Only Stripe's test card numbers work while Stripe is on. Set `PAYMENT_GATEWAY=fake` to go back to the offline gateway.

---

## Appendix — what each dependency does

| Package | Purpose |
|---|---|
| `Flask` | The web framework serving the API |
| `Werkzeug` | Flask's underlying HTTP layer; pinned so it cannot drift |
| `Flask-Cors` | Lets the browser call Flask from the Vite dev server's origin |
| `PyMySQL` | Pure-Python MySQL driver — no compiler needed on any platform |
| `cryptography` | Required by PyMySQL to authenticate against MySQL 8 |
| `python-dotenv` | Loads `.env` so credentials stay out of the code |
| `pytest` | Backend test runner |
| `pytest-cov` | Coverage reporting, per the test plan |
| `react`, `react-dom` | The UI library |
| `react-router-dom` | Page routing |
| `mapbox-gl` | The interactive delivery map on order tracking |
| `vite`, `@vitejs/plugin-react` | Dev server and build tool |
| `tailwindcss`, `@tailwindcss/vite` | Styling; v4 is a Vite plugin with no config file |
| `vitest`, `jsdom`, `@testing-library/*` | Frontend test runner and component testing tools |

Stripe needs no package: the backend talks to Stripe's API directly.
