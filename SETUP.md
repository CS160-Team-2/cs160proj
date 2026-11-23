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
| **Chrome** | any recent | Optional. Only for the browser tests in Part 3 |

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
- Choose `backend/schema/schema.sql` from the repository.
- Click the **⚡ lightning-bolt** button (*Execute all*), or press **Ctrl+Shift+Enter** / **⌘⇧Enter**.

Prefer the command line? From the repository root, as root:

```bash
mysql -u root -p < backend/schema/schema.sql
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

Every test should pass (768 tests, about 3 minutes). The backend tests are in `backend/test/`. They use their own `ofs_test` database, which they rebuild before each test, so they never touch the data in `ofs`. They need MySQL running and `schema.sql` run once.

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

**Check — the frontend tests pass** (in a new terminal, or stop Vite first):

```bash
cd frontend
npm run test:run
```

All 321 tests should pass (about 20 seconds). They are in `frontend/test/`, in the same folders as `frontend/src`.

**Optional — the browser tests.** These drive a real Chrome through the whole site. With Flask and Vite stopped (the tests start their own) and the demo data in place:

```bash
cd frontend
E2E_CHANNEL=chrome npm run e2e
```

59 tests pass (4 more are skipped unless you turn on the order tests; see the README). They take about 2 minutes. They leave your data as they found it. The tests are in `frontend/browser_test/`.

---

## Part 5 — Verify the whole system

With Flask (terminal 1) and Vite (terminal 2) running, open `http://localhost:5173`.

### Demo accounts

Created by `schema.sql`, for local testing only.

| Role | Email | Password | After signing in |
|---|---|---|---|
| Customer | `customer@ofs.test` | `customer-pass-1` | Back to the shop; **Profile** and **Orders** |
| Employee | `employee@ofs.test` | `employee-pass-1` | The inventory console at `/inventory` |
| Manager | `manager@ofs.test` | `manager-pass-1` | The manager order monitor at `/manager` |

Everyone signs in on the same page (`/login`) and the role decides where they land. The public sign-up page only ever creates customers; staff accounts are created by a manager (the **Staff** page).

### Check the customer path

1. **Browse.** The home page shows featured and most sold products. The Products page filters by category and price, searches by name or by product number (the number is shown under each product name), and sorts. Peaches and raspberries show **Unavailable**.
2. **Add to cart.** Open a product, set a quantity and press *Add to cart*. The cart count in the header goes up. This works without signing in.
3. **Check the 20 lb delivery rule.** Add **6** bags of apples (3.00 lb each) and **1** bunch of bananas (2.00 lb). The cart must show:

   ```
   Total weight   20.00 lb
   Delivery       $10.00        ← not Free
   ```

   Exactly 20.00 lb is charged. With **5** bags of apples and 1 bunch of bananas (17.00 lb) delivery is Free. Under the totals the cart says how far the order is from the line (for example "so 3.00 lb more would add the charge").
4. **Check out as a guest.** Press checkout without signing in. Enter a name, email, phone and a delivery address within 25 miles of San Jose (for example `1 Washington Sq`, `San Jose`, `CA`, `95192`), then pay with card `4242 4242 4242 4242`, any future expiry and any 3-digit code. You land on **Orders** with your order number. With a live map provider (see Optional: live mapping) a made-up address such as `123 Fake Dr` or one in San Francisco is refused with a clear message; with the offline map any address with a house number is accepted.
5. **Track a guest order later.** Choose **Track** in the top bar and enter the order number plus the email you used. (On a phone, **Track** and **Orders** are in the profile menu.)
6. **Check out signed in.** Sign in as the demo customer, add something, and check out again. The saved name and address are filled in, and the order appears under **Orders**. Ticking **Remember me** keeps you signed in for 14 days.
7. **Declined card.** Pay with `4000 0000 0000 0002`. You stay on checkout with an error, and the cart is unchanged.

### Check the employee path

1. Sign out, then sign in as `employee@ofs.test`. You land on the inventory console. The profile menu shows only staff pages: **Inventory**, **Customer orders** and **Delivery tracking**.
2. Search for a product, or filter by availability or category.
3. Change a product's stock with a number such as `10` or `-3` and choose a **reason** (it is required). Press **History** on the product to see who changed what, when and why. Stock cannot go below zero.
4. Change a product's **low-stock level** and press Save; the LOW flag follows it.
5. Press **Add product** and fill in name, category, price and weight (weight is required). Choose a picture (JPEG, PNG or WebP, up to 5 MB) to upload one. Open the shop and check the new product appears. **Unlist** hides a product but keeps it in the records.
6. Open **Customer orders**: every order with its status, read-only. Open **Delivery tracking**: the orders waiting for a trip, the vehicles, and the trips with their routes. Employees cannot open the manager pages or upload manifests.

### Check the manager path

1. Sign in as `manager@ofs.test`. The manager order monitor opens. Find an order, open it to see its items, address and payment, and press **Mark ready for delivery**.
2. On **Delivery**, tick the waiting order, pick a vehicle (each carries at most 10 orders and 200 lb) and **Create trip**, then **Dispatch**. With `VEHICLE_SIMULATION_SECONDS=20` the vehicle delivers one stop every 20 seconds. Open the customer's tracking page to watch it.
3. On **Inventory**, under **Delivery manifest**, upload `examples/delivery-manifests/delivery-good.csv`. The preview shows each product's stock now and after (peaches and raspberries go from 0 back into stock); press **Apply**. Then upload `delivery-with-problems.csv`: every problem is listed by line and nothing is saved. Uploading the good file again is refused as already applied.
4. Look at **Staff** (add or deactivate an employee), **Problems** (declined payments and orders that could not be scheduled) and **Vehicles**.

Applying a manifest, ordering and dispatching change your local data. To put the demo data back, run `python backend/reset_db.py` from the repository root with the virtual environment active (no root password needed).

## Security and HTTPS

What the app already does: passwords are stored hashed, every database query is parameterised (so text such as `' OR '1'='1` is only text), the sign-in cookie is HTTP-only and same-site, answers carry `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` headers, and account, cart and order answers are never cached by the browser.

**Rate limits.** Wrong passwords at sign-in, order look-ups that find nothing, and wrong passwords when changing a password or deleting an account are counted; after too many the answer is "Too many … Please wait N minutes" (HTTP 429). Correct tries are never counted. The numbers are in `backend/.env.example`. The counts are kept in the Flask process's memory, so a restart clears them. Behind Apache, set `TRUSTED_PROXIES=1` so each visitor is counted separately.

**Passwords** must be 8 to 128 characters.

**Putting the site on HTTPS** (a server other than your laptop):
1. Serve the site over HTTPS (see `deploy/APACHE.md`).
2. In `backend/.env` set your own long random `SECRET_KEY`, and `SESSION_COOKIE_SECURE=1`. Flask refuses to start with `SESSION_COOKIE_SECURE=1` and the development key.
3. Set `TRUSTED_PROXIES=1` if Apache sits in front of Flask, and `FRONTEND_ORIGIN` to the site's address.
4. Use live (not test) payment keys only after the team agrees; this project is built for test keys.

## Running behind Apache (production-like)

The assignment recommends Apache as the web server. In production one Apache serves the built React site and forwards `/api` to Flask, so the browser sees a single address and no CORS is involved. The full step-by-step guide, with Windows (XAMPP) and macOS instructions, is [`deploy/APACHE.md`](deploy/APACHE.md); the configuration is [`deploy/ofs.conf`](deploy/ofs.conf).

In short:

1. Build the site for the same origin: `cd frontend`, then `VITE_API_BASE= npm run build` (PowerShell: `$env:VITE_API_BASE=""; npm run build`).
2. Enable Apache's `rewrite`, `proxy` and `proxy_http` modules, and publish the build and the virtual host (`deploy/publish.sh` on macOS copies the build into a folder Apache may read; it asks for your administrator password).
3. Keep Flask running on port 5001 and open `http://localhost:8080`.
4. In `backend/.env` add `TRUSTED_PROXIES=1` so the rate limits see each visitor.

The configuration was tested with Apache 2.4.66: the site is served, page addresses such as `/products` come back from the app, `/api` reaches Flask (39 products), and sign-in, cart and checkout work through the one address. A check you can repeat: `curl http://localhost:8080/api/health` should return `"ok": true`.

## Product pictures

Employees upload product pictures in the inventory console. The picture is saved **in the database** (table `product_pictures`), and `products.image_key` holds a short reference (`upload:<random name>.jpg`). The 39 seeded products keep the pictures bundled in `frontend/src/assets`.

- Because the pictures are in the database, they move with it: a backup or a copy of the database carries them too. Nothing else needs copying.
- If your database was made before this change, run `backend/schema/updates/add_product_pictures.sql` once (see "Updating your database after a pull"). Pictures that are still files in `backend/uploads/products/` keep working: each one is copied into the database the first time it is shown.
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

Then restart Flask. The backend needs no extra package.

To show Stripe's own card field on the checkout page, also copy the **Publishable key** (starts with `pk_test_`, same page of the dashboard) into `frontend/.env`:

```
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...your publishable key...
```

Restart Vite. The page shows Stripe's fields only when the backend gateway is `stripe` **and** this key is set; otherwise it keeps the built-in test form. The publishable key is meant for the browser. The secret `sk_` key must never go in `frontend/.env`.

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

The payment, or the declined attempt, appears in the Stripe dashboard under **Payments**.

**With the publishable key set**, the card form is Stripe's own, so any [Stripe test card](https://docs.stripe.com/testing) works (use any future expiry, any CVC and any ZIP code). **Without it**, the built-in form only accepts the five numbers above.

**Apple Pay and Google Pay** buttons appear above the card form only when the customer's browser and device support them. They need more setup than cards:

- Stripe requires HTTPS and a registered domain, and `localhost` does not qualify. To try them, expose the site on an HTTPS address (for example with a tunnel such as ngrok) and add that domain in the Stripe dashboard under **Settings, Payment methods, Payment method domains**.
- Apple Pay needs Safari on an Apple device with a card in Wallet. Google Pay needs Chrome signed in to a Google account with a saved card.
- Stripe's wallet testing page has the details: https://docs.stripe.com/testing/wallets

The buttons were built to Stripe's documentation but have not been tried on a real device yet. PayPal is a separate payment method, set up in the next section.

### If something goes wrong

- **Checkout fails with a server error, and the Flask terminal mentions `STRIPE_SECRET_KEY`:** the key is missing from `.env`, or it is a live key. Flask only checks the key at the first checkout, not when it starts.
- **Every checkout says it could not reach the payment service:** the key is wrong or was replaced in the dashboard. Copy it again. If that is not it, check your internet connection.
- **A key leaked:** go to **Developers → API keys** in the Stripe dashboard and roll (replace) it. Because it is a test key, no real money was at risk.

To go back to the offline fake, set `PAYMENT_GATEWAY=fake` and restart Flask.

---

## Optional: Turn on PayPal (sandbox)

PayPal is offered on the checkout page only when the backend has PayPal keys. Without them nothing changes. With them, the payment section shows two radio buttons, **Credit or debit card** (Stripe) and **PayPal**. Choosing PayPal replaces the card form and the Place Order button with PayPal's own button. Only the PayPal button is shown: cards are paid with the Stripe card field, so PayPal's Pay Later and its Debit or Credit Card button are switched off. The money is taken only after the customer approves it at PayPal, and the server checks that the approved amount equals the order total before it captures it.

**Sandbox only.** The sandbox is PayPal's test system and never moves real money. OFS refuses a live PayPal account unless you set both `PAYPAL_ENV=live` and `PAYPAL_ALLOW_LIVE=1`, which nobody on this project should do.

### 1. Create a sandbox app

1. Sign in at [developer.paypal.com](https://developer.paypal.com) with any PayPal account. A free personal account is enough for the sandbox. A business account is only needed to go live, which this project never does.
2. Open **Apps & Credentials** and make sure **Sandbox** is selected (not Live). Menu names can differ slightly from this guide.
3. Press **Create App**, choose the **Merchant** type, and give it a name.
4. Copy the app's **Client ID** and **Secret**.

### 2. Put them in `backend/.env`

```
PAYPAL_CLIENT_ID=...your sandbox client id...
PAYPAL_CLIENT_SECRET=...your sandbox secret...
```

Restart Flask. No key is needed in `frontend/.env`: the checkout page reads the public client id from the backend. **Never commit the secret or paste it into chat.**

### 3. Try it

1. Add something to the cart and go to checkout. (Guests fill in their details first. The PayPal buttons refuse to start until the details are complete.)
2. Choose **PayPal**, then press the PayPal button.
3. Sign in with a **sandbox buyer** account. In the developer dashboard, open **Testing tools, Sandbox accounts**: a personal (buyer) account is created for you, and its email and password are shown there.
4. Approve the payment. The order is placed, and the order page says "Paid with PayPal".


### If something goes wrong

- **No PayPal radio button on checkout:** both keys must be set in `backend/.env` and Flask restarted. `GET /api/payments/config` shows `"paypal": {"enabled": true, ...}` when it is on.
- **"PayPal refused our credentials" in the Flask terminal:** the Client ID and Secret do not belong to the same sandbox app, or a live key was used in sandbox.
- **"The PayPal payment does not match this order's total":** the cart changed after the PayPal order was created. Start the payment again.
- **The PayPal popup is blocked:** allow pop-ups for the site.
- To turn PayPal off, remove the keys or set `PAYPAL_ENABLED=0` and restart Flask.

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

**After pulling new code**, run `npm install` in `frontend/` and `pip install -r requirements.txt` (venv active) if `package.json` or `requirements.txt` changed. If `backend/schema/schema.sql` changed, update your database as in [Updating your database after a pull](#updating-your-database-after-a-pull).

## Updating your database after a pull

**In short:** everyone has their own database on their own computer, so when a pull changes `backend/schema/schema.sql`, each person updates their own copy. You have two choices: rebuild from scratch, which is simplest but erases your local data, or run the small update scripts, which keep it.

**Option A: rebuild from scratch (erases your local data).** This resets `ofs` to the demo data; orders, accounts you registered and products you added or edited are lost.

```bash
python backend/reset_db.py                     # no root password needed; run from the repository root, venv active
```

or run `backend/schema/schema.sql` as root exactly as in [Part 2](#part-2--set-up-the-database-in-mysql-workbench):

```bash
mysql -u root -p < backend/schema/schema.sql
```

**Option B: run the update scripts (keeps your local data).** Each script is in `backend/schema/updates/`, is safe to run more than once, and only adds what is missing. Run the ones your database lacks, **in this order**:

| Order | Script | What it adds | The error you get without it |
|---|---|---|---|
| 1 | `add_delivery_manifests.sql` | The `delivery_manifests` table (manager restocking from a CSV) | Uploading a manifest fails: missing table `delivery_manifests` |
| 2 | `add_manifest_ids.sql` | A manifest ID on each manifest; an ID can be applied once | Uploading a manifest fails: unknown column `supplier_manifest_id` |
| 3 | `add_product_pictures.sql` | The `product_pictures` table (uploaded pictures now live in the database) | Uploading a product picture fails: unknown table `product_pictures` |

Run a script with MySQL Workbench (**File → Open SQL Script**, pick the file, press the lightning bolt) or from the repository root:

```bash
mysql -u root -p < backend/schema/updates/add_product_pictures.sql
```

*If you use the Docker database from Part 2.4 as your `ofs` database,* start it first, then from the repository root:

```bash
docker exec -i ofs-mysql-test mysql -ucs160team2 -pteam2_password < backend/schema/updates/add_product_pictures.sql
```

MySQL may warn that using a password on the command line is insecure. That is expected for this shared demo password and can be ignored.

**Check that it worked:** restart Flask, sign in as the manager (`manager@ofs.test`), open **Inventory** and choose a CSV file under **Delivery manifest**: you should see a preview table, not an error. A manifest needs the columns `manifest_id`, `product_name` and `quantity`, every line carries the same manifest ID, and any product name that contains a comma must be in double quotes:

```text
manifest_id,product_name,quantity
DM-1001,"Organic Apples, 3 lb bag",24
DM-1001,Organic Broccoli Crown,30
```

Sample files are in `examples/delivery-manifests/`. Pictures that were uploaded before the change and are still files in `backend/uploads/products/` keep working: each is copied into the database the first time it is shown.

## Configuration reference

Backend settings go in `backend/.env`; frontend settings in `frontend/.env`. Both are ignored by Git. Never commit a key.

| Setting | Default | Purpose |
|---|---|---|
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | `127.0.0.1`, `3306`, `cs160team2`, `team2_password`, `ofs` | Database connection |
| `FLASK_PORT` | `5001` | Port Flask listens on |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The only address allowed to call the API |
| `SECRET_KEY` | development key | Signs the sign-in cookie. Set your own on any shared server |
| `SESSION_COOKIE_SECURE` | off | `1` on HTTPS: the sign-in cookie is sent only over HTTPS (needs your own `SECRET_KEY`) |
| `TRUSTED_PROXIES` | `0` | `1` behind Apache, so rate limits count each visitor |
| `RATE_LIMIT_ENABLED` and `RATE_LIMIT_*` | on | Limits on failed sign-ins and look-ups; see Security and HTTPS |
| `CART_SESSION_DAYS` | `14` | How many days a guest's cart and a customer's sign-in last after their last visit. Each visit extends it. Staff sessions end with the browser |
| `PAYMENT_GATEWAY` | `fake` | `fake` or `stripe` |
| `STRIPE_SECRET_KEY`, `STRIPE_CURRENCY`, `STRIPE_ALLOW_LIVE` | none, `usd`, `0` | A `sk_test_` key, used when the gateway is `stripe`; live keys are refused unless `STRIPE_ALLOW_LIVE=1` |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | none | PayPal sandbox app keys. Both set means checkout offers PayPal |
| `PAYPAL_ENV`, `PAYPAL_CURRENCY`, `PAYPAL_ENABLED`, `PAYPAL_ALLOW_LIVE` | `sandbox`, `USD`, `1`, `0` | Sandbox or live (live also needs `PAYPAL_ALLOW_LIVE=1`), currency, and an off switch (`0`) |
| `MAP_PROVIDER` | `fake` | `fake`, `mapbox` or `google` |
| `MAPBOX_ACCESS_TOKEN`, `GOOGLE_MAPS_API_KEY` | none | Server-side map keys |
| `STORE_LATITUDE`, `STORE_LONGITUDE` | San Jose (SJSU) | Where the store is, for routes and the delivery area |
| `SERVICE_RADIUS_MILES` | `25` | Farthest an address may be from the store, in straight-line miles |
| `VEHICLE_LINK`, `VEHICLE_SIMULATION_SECONDS` | `simulated`, `20` | The simulated vehicle completes one stop every N seconds after dispatch. `0` means stops are only completed when reported |
| `TAX_RATE` | `0.09375` | Sales tax rate |
| `PRODUCT_IMAGE_DIR` | `backend/uploads/products` | Only for old pictures that are still files; they are copied into the database when first shown |
| `VITE_API_BASE` (frontend) | `http://localhost:5001` | Backend address. Empty means the same server, as in the Apache deployment |
| `VITE_MAPBOX_ACCESS_TOKEN` (frontend) | none | A Mapbox **public** `pk.` token for the interactive delivery map |
| `VITE_STRIPE_PUBLISHABLE_KEY` (frontend) | none | A Stripe **publishable** `pk_test_` key for Stripe's own card field; empty keeps the built-in test form |

`backend/.env.example` and `frontend/.env.example` list every setting with a one-line description.

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
The database layout changed. Run `backend/schema/schema.sql` again as root (Part 2). This resets `ofs` to the seed data. To keep your data instead, see [Updating your database after a pull](#updating-your-database-after-a-pull); for example, an error about a missing `delivery_manifests` table is fixed there with Option B.

**15. The shop says "Cannot reach the store right now"**
Flask is not running, or Vite is not on port 5173 (see #6 and #11). Check <http://localhost:5001/api/health> in a browser.

**16. An uploaded product picture does not show**
Check that Flask is running and that your database has the `product_pictures` table (run `backend/schema/updates/add_product_pictures.sql` if not). Pictures are stored in the database, so they appear on any machine that uses the same database; a laptop with its own local database only shows the pictures uploaded to that database.

**17. Checkout with Stripe fails or every card is refused**
See *If something goes wrong* under Stripe test payments above. Only Stripe's test card numbers work while Stripe is on. Set `PAYMENT_GATEWAY=fake` to go back to the offline gateway.

**18. "Too many failed sign-in attempts … Please wait N minutes"**
The rate limit for wrong passwords was reached (8 wrong tries for one account, or 30 from one connection, in 10 minutes). Wait the time shown, or restart Flask, which clears the counts. While testing you can set `RATE_LIMIT_ENABLED=0` in `backend/.env`. See Security and HTTPS.

**19. "We could not find that address" or "we only deliver within 25 miles"**
With a live map provider, the address must be a real one close to the San Jose store. Check the spelling, the city and the ZIP code. With `MAP_PROVIDER=fake` any address with a house number is accepted.

**20. Flask will not start: "SECRET_KEY must be set when SESSION_COOKIE_SECURE=1"**
`SESSION_COOKIE_SECURE=1` is for HTTPS sites and needs your own long random `SECRET_KEY` in `backend/.env`. On your laptop, remove `SESSION_COOKIE_SECURE` from `.env`.

**21. Uploading a delivery manifest fails**
Run the update scripts your database is missing (see Updating your database after a pull). If the preview lists problems instead, fix the lines it names; every line needs the same `manifest_id`, and an ID that was already applied is refused.

**22. The Apache site shows the page but no data, or a 403**
`/api` is not being forwarded to Flask, or Apache cannot read the folder. See the Troubleshooting section of [`deploy/APACHE.md`](deploy/APACHE.md); on macOS use `deploy/publish.sh` rather than pointing Apache at a folder inside Desktop.

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
| `@playwright/test` | Real-browser tests in `frontend/browser_test` |
| `@stripe/stripe-js`, `@stripe/react-stripe-js` | Stripe's own card field and wallet buttons |
| `@paypal/react-paypal-js` | PayPal's button |

The backend needs no package for Stripe, PayPal, Mapbox or Google: it calls their web APIs directly. The frontend uses `@stripe/stripe-js` and `@stripe/react-stripe-js` (Stripe's card field), `@paypal/react-paypal-js` (PayPal's button) and `@playwright/test` (the real-browser tests).

Why PyMySQL and not `mysqlclient`: `mysqlclient` is a C extension that needs a compiler and the MySQL client headers (Visual C++ Build Tools on Windows, `brew install mysql-client` on Apple Silicon). PyMySQL installs the same way everywhere. Use Python 3.11 or 3.12, not 3.13: some packages have no prebuilt files for 3.13 yet, which forces a build from source.

