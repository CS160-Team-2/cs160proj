# Running the Spike on Your Mac

Written for **macOS on Apple Silicon** — your machine. `SETUP.md` is the version for the whole team including the Windows members; this is the shorter one with no Windows branches.

Each step says **what you're doing**, the **commands**, **what to look for**, and **what it proves**. That last part matters — you're not just getting it working, you're collecting evidence for the Part II prototyping task.

Budget about an hour if nothing is installed, twenty minutes if everything is.

---

## Step 0 — Check what you already have

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto
bash check-setup.sh
```

You get a list of PASS / WARN / FAIL. **WARN items are fine** — they're things the walkthrough creates as you go (the virtual environment, `node_modules`, the database). **FAIL items must be installed first.**

Re-run this script any time. It changes nothing.

---

## Step 1 — Install anything that failed

Only do the ones the script flagged.

**Python 3.12** — [python.org/downloads/macos](https://www.python.org/downloads/macos/), *macOS 64-bit universal2 installer*. Not 3.13: some packages have no wheels for it yet and pip falls back to compiling.

**Node.js LTS** — [nodejs.org](https://nodejs.org/), **macOS Installer (.pkg) ARM64**. Tailwind v4 needs Node 20 or newer.

**MySQL Community Server** — [dev.mysql.com/downloads/mysql](https://dev.mysql.com/downloads/mysql/), *macOS ARM, 64-bit DMG Archive*. During install keep **Use Strong Password Encryption**, set a root password, and write it down. Afterwards open **System Settings → MySQL** and click **Start MySQL Server**, then tick *Start MySQL when your computer starts up*.

**MySQL Workbench** — [dev.mysql.com/downloads/workbench](https://dev.mysql.com/downloads/workbench/). If no ARM build is listed for your macOS version, the Intel one runs under Rosetta and macOS will offer to install it.

**Git** — `xcode-select --install`.

Re-run `bash check-setup.sh` until nothing FAILs.

---

## Step 2 — MySQL

**What you're doing:** creating the database, a user, the tables, and three products.

Open **MySQL Workbench**. Click your **local connection** (create one if there isn't one: hostname `127.0.0.1`, port `3306`, username `root`). Enter your root password.

Then:

1. **File → Open SQL Script…**
2. Choose `cs160_proj_proto/backend/schema.sql`
3. Click the **⚡ lightning bolt** (or press **⌘⇧Enter**)

**What to look for.** The Output panel at the bottom shows green ticks, no red. Result grids show:

| check_name | result |
|---|---|
| Products loaded: | 3 |
| Customers loaded: | 1 |
| MySQL version: | 8.0.x or 8.4.x |

In the left **Navigator**, click the refresh icon next to SCHEMAS. `ofs` appears. Expand it → Tables → you'll see `products`, `customers`, `carts`, `cart_items`. Right-click `products` → **Select Rows** to see the three items.

**Try it yourself** — paste this in a query tab and run it:

```sql
USE ofs;
SELECT name, unit_weight_lb, unit_weight_lb * 10 AS ten_of_them FROM products;
```

The lemon row shows `0.10` and `1.00`. Exactly 1.00, not 0.9999999. That's MySQL's `DECIMAL` type doing its job — the foundation the whole delivery-charge rule rests on.

**What it proves:** MySQL runs on your Mac, Workbench connects, the schema loads, `DECIMAL` arithmetic is exact, and the `cs160team2` user exists so you never have to put your root password in a project file.

---

## Step 3 — Python and Flask

**What you're doing:** creating an isolated Python environment, installing the backend's dependencies, and starting the API.

Open **Terminal**:

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto/backend

python3 -m venv .venv
source .venv/bin/activate
```

Your prompt now starts with `(.venv)`. That's the whole point of a virtual environment — packages install into this folder instead of polluting your system Python, so the project can't break anything else on your Mac, and a teammate with different packages installed still gets identical behaviour.

```bash
python -m pip install --upgrade pip
pip install -r ../requirements.txt
cp .env.example .env
```

**What to look for.** `pip list` shows Flask, PyMySQL, cryptography, pytest and friends. Nothing should have tried to compile — every package here ships a prebuilt ARM64 wheel, which is exactly why `requirements.txt` uses PyMySQL rather than `mysqlclient`.

Now start the API:

```bash
python app.py
```

You should see `Running on http://127.0.0.1:5001`. **Leave this terminal running.**

> Port 5001, not Flask's usual 5000, because macOS uses 5000 for AirPlay Receiver. You'd have hit "Address already in use" immediately.

Open a **second Terminal tab** (⌘T) and try the API:

```bash
curl http://localhost:5001/api/health
curl http://localhost:5001/api/products
```

**What to look for.** The second response includes:

```json
"mysql_version": "8.0.x",
"weight_python_type": "Decimal",
```

`"Decimal"` is the answer you want. If it said `"float"`, the delivery-charge rule couldn't be trusted no matter how carefully it was written.

**What it proves:** Flask runs, PyMySQL connects from Python to MySQL, and `DECIMAL` survives the journey from the database into Python.

---

## Step 4 — Pytest

**What you're doing:** running two test files that prove two different things. Understanding the difference is the point.

In your second terminal (with `.venv` active — `source .venv/bin/activate` if the prompt doesn't show it):

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto/backend
source .venv/bin/activate

pytest test_rules.py -v
```

14 tests. These check the **arithmetic** — that 19.99 lb is free and 20.00 lb is charged. They need no database and would pass with any technology stack. They're not a feasibility test; they're here because pytest itself is in your Tools table, and because this rule is worth de-risking early.

```bash
pytest test_integration.py -v
```

**These are the feasibility tests.** 13 of them, each answering something you cannot learn from documentation because the answer depends on your specific install:

- Does PyMySQL connect from macOS with these credentials?
- Does a `DECIMAL` column arrive as `Decimal` or `float`?
- Do writes actually commit — checked by reading back on a *different* connection, so an uncommitted transaction can't fool the test?
- Are foreign keys enforced? (InnoDB yes; MyISAM would silently accept garbage.)
- Does MySQL enforce `CHECK` constraints? **It ignored them before version 8.0.16.** If that test fails, your "weight is required" rule isn't actually being enforced by the database and you'd never have noticed.

Run everything:

```bash
pytest -v
```

**What to look for.** 27 passed. If the integration tests are *skipped*, MySQL isn't reachable — go back to Step 2.

**What it proves:** pytest works on Apple Silicon, and the Flask↔MySQL seam behaves correctly under real conditions.

---

## Step 5 — React, Vite and Tailwind

**What you're doing:** installing the frontend and starting the dev server.

Open a **third Terminal tab**. Leave Flask running in the first.

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto/frontend
npm install
```

Do **not** use `sudo`. If you hit permission errors: `sudo chown -R $(whoami) ~/.npm` and try again.

```bash
npm run dev
```

Vite prints `Local: http://localhost:5173/`. Open it in Chrome.

**What to look for.** Four checks, all green:

1. **React reaches Flask across origins** — proves CORS is configured. React is on 5173, Flask on 5001; the browser treats those as different origins and would block the request without `Flask-Cors`.
2. **Flask reaches MySQL and reads DECIMAL** — shows your MySQL version.
3. **Tailwind is compiling** — if the boxes are coloured and spaced rather than plain black text, Tailwind's classes are being applied. That's all this check is: styling either happened or it didn't.
4. **Full chain** — the interactive one.

**Try it yourself.** Set **6** apple bags and **20** lemons, press *Run cart check*:

```
Total weight   20.00 lb
Delivery       $10.00        ← not FREE
```

6 × 3.00 + 20 × 0.10 = exactly 20.00 lb. Free delivery applies only *below* 20, so this is charged. Now change to **5** bags + **20** lemons (17.00 lb) and it should say FREE.

**See CORS for yourself.** Open Chrome DevTools (⌥⌘I) → **Network** tab → press *Run cart check* again. You'll see **two** requests to `cart-check`: an `OPTIONS` then a `POST`. The `OPTIONS` is the CORS **preflight** — the browser asking Flask "am I allowed to send this?" before sending it. That's the thing that breaks when CORS isn't configured, and it only happens on requests with a JSON body, which is why the spike includes one deliberately.

**What it proves:** Vite builds and serves React, Tailwind compiles, and the browser can reach Flask across origins including the preflight case.

---

## Step 6 — The two use cases, without any UI

**What you're doing:** exercising the main use cases directly against the API. No interface needed — this is about proving the data path works.

In your second terminal:

### Use case 1 — a customer chooses a product, and it's stored

```bash
# Anna (customer 1) picks 6 bags of apples
curl -X POST http://localhost:5001/api/cart/items \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 2, "quantity": 6}'

# ...and 20 lemons
curl -X POST http://localhost:5001/api/cart/items \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 1, "quantity": 20}'

# Read the cart back
curl http://localhost:5001/api/cart/1
```

**What to look for.** `"total_weight_lb": "20.00"` and `"delivery_fee": "10.00"`.

Now confirm it's genuinely in the database, not in Flask's memory. In **MySQL Workbench**:

```sql
USE ofs;
SELECT c.customer_id, p.name, ci.quantity
FROM carts c
JOIN cart_items ci ON ci.cart_id = c.cart_id
JOIN products p ON p.product_id = ci.product_id;
```

Two rows. **Stop Flask** (Ctrl+C in terminal 1), start it again, and re-run `curl http://localhost:5001/api/cart/1` — the cart is still there. That's the proof: the data survived the process restarting because it lives in MySQL.

### Use case 2 — a store employee adds and removes a product

```bash
# Bob adds a new product
curl -X POST http://localhost:5001/api/admin/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Organic Carrots, 2 lb bag", "price": "3.49", "unit_weight_lb": "2.00"}'
```

Note the returned `product_id` and `"appears_in_catalog": true`. Refresh `http://localhost:5173` — the carrots are in the list.

```bash
# Try to add one with no weight — the DATABASE should refuse
curl -X POST http://localhost:5001/api/admin/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Weightless Item", "price": "1.00", "unit_weight_lb": "0"}'
```

**What to look for.** A `409` with `"REJECTED_BY_DATABASE"`. That rejection comes from the `CHECK (unit_weight_lb > 0)` constraint in `schema.sql`, not from Python. The rule holds even if application code forgets to validate.

```bash
# Remove the carrots (use the id you got above, e.g. 4)
curl -X DELETE http://localhost:5001/api/admin/products/4
```

**What to look for.**

```json
"still_in_catalog": false,
"row_still_exists": true
```

That's the interesting finding. "Remove a product" **cannot** mean `DELETE FROM products` — a customer might have it in their cart, and in the real system an order would reference it. So it's a soft delete: `is_listed = FALSE`. The product disappears from the shop; the row survives for history. Worth writing into your Part II notes.

**What it proves:** both main use cases work end to end through Flask and MySQL, the database enforces its own rules, and removal has to be a soft delete.

---

## Step 7 — Apache

**What you're doing:** serving the app the way it will actually ship — Apache serving the built React files and forwarding `/api` to Flask.

macOS includes Apache:

```bash
httpd -v
sudo apachectl start
```

Visit `http://localhost` — "It works!" means Apache is running.

**Enable the three modules** Apache ships with switched off (backs up the file first):

```bash
sudo cp /etc/apache2/httpd.conf /etc/apache2/httpd.conf.backup

sudo sed -i '' \
  -e 's|^#\(LoadModule proxy_module .*\)|\1|' \
  -e 's|^#\(LoadModule proxy_http_module .*\)|\1|' \
  -e 's|^#\(LoadModule rewrite_module .*\)|\1|' \
  /etc/apache2/httpd.conf
```

**Build the frontend** — this is different from `npm run dev`:

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto/frontend
VITE_API_BASE= npm run build
```

The empty `VITE_API_BASE=` matters. It makes every API call a **relative** URL (`/api/health` instead of `http://localhost:5001/api/health`), which is what lets Apache serve both from one origin. Output goes to `frontend/dist/`.

**Install the config.** Apache only reads from `/etc/apache2/`, so `deploy/ofs.conf` has to be copied there — and its `__DIST__` placeholder replaced with your real path. One command does both:

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto

sed "s|__DIST__|$(pwd)/frontend/dist|g" deploy/ofs.conf \
  | sudo tee /etc/apache2/other/ofs.conf > /dev/null
```

`sed` swaps the placeholder for your actual folder; `sudo tee` writes the result into Apache's config directory. Nothing else needs editing — your `httpd.conf` already ends with `Include /private/etc/apache2/other/*.conf`, so anything dropped in there loads automatically. The `Listen 8080` line is inside `ofs.conf` as well.

Verify the path was substituted, then restart:

```bash
grep DocumentRoot /etc/apache2/other/ofs.conf     # your real path, not __DIST__
sudo apachectl configtest                          # expect "Syntax OK"
sudo apachectl restart
```

Make sure Flask is running, then open **`http://localhost:8080`**.

**What to look for.** The same page — but now open DevTools:

- **Network** tab: the request URL is `http://localhost:8080/api/health`, **not** `:5001`.
- **Console** tab: **no CORS messages at all**, and no `OPTIONS` preflight in Network.

That's the finding. Behind Apache everything is one origin, so CORS simply doesn't apply. It's a development-only concern.

**Prove the proxy is doing the work.** Comment out the two `ProxyPass` lines, `sudo apachectl restart`, reload. The page still loads but the checks fail with 404s — Apache is looking for a *file* called `api/health`. Uncomment, restart, green again.

**What it proves:** Apache serves the production build, `mod_proxy` forwards `/api` to Flask, and the whole stack works with no CORS.

---

## Step 8 — Record what you found

Fill in the table at the bottom of `README.md` and the one in `deploy/APACHE.md`, and put them in the Part II document as the outcome of the prototyping task. Note the actual version numbers — "MySQL 8.0.36, Node 22.11, Tailwind 4.0.x" is more useful to your team than a tick.

Also worth recording, because these are findings rather than just checks:

- CORS is a development-only concern; Apache removes it.
- `DECIMAL` survives MySQL → PyMySQL → Python, and must be sent to the browser as a **string** so React can't do float arithmetic on it.
- "Remove a product" must be a soft delete.
- MySQL enforces `CHECK` constraints only from 8.0.16 — note the version you tested on.

---

## Daily routine after this

Three terminal tabs:

| Tab | Command |
|---|---|
| 1 — Flask | `cd cs160_proj_proto/backend && source .venv/bin/activate && python app.py` |
| 2 — Vite | `cd cs160_proj_proto/frontend && npm run dev` |
| 3 — work | `curl`, `pytest`, `git` |

MySQL runs as a background service and starts with your Mac. Apache only matters when you're testing the deployment.

---

## If something breaks

Re-run `bash check-setup.sh` first — it catches most of it. Otherwise:

| Symptom | Cause |
|---|---|
| `Address already in use` on 5001 | Flask is already running in another tab |
| `Can't connect to MySQL server` | System Settings → MySQL → Start MySQL Server |
| `Access denied for user 'cs160team2'` | `schema.sql` didn't finish — re-run it in Workbench |
| `cryptography is required for...` | Stale install; re-run `pip install -r requirements.txt` |
| `externally-managed-environment` | The venv isn't active — prompt must show `(.venv)` |
| CORS error in console | Flask isn't running, or `FRONTEND_ORIGIN` is `127.0.0.1:5173` instead of `localhost:5173` — the browser treats those as different origins |
| Integration tests all skipped | MySQL not reachable — Step 2 |
| Apache `500` on `/api` | `mod_proxy_http` not enabled — `mod_proxy` alone isn't enough |
