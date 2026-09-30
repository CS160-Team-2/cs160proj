# OFS — Environment Setup

Step-by-step setup for the feasibility spike, verified for **Windows 10/11 (x86-64)** and **macOS on Apple Silicon (M1–M5)**.

Follow the parts in order. Each ends with a check — if the check fails, stop and look at [Troubleshooting](#troubleshooting) rather than continuing. Allow about 45 minutes the first time, most of it waiting for installers.

---

## Part 0 — What you are installing

| Software | Version | Why |
|---|---|---|
| **Python** | 3.11 or 3.12 | Backend language. **Not 3.13** — see Troubleshooting #9 |
| **Node.js** | 20 LTS or 22 LTS | Runs Vite. Tailwind v4 needs Node 20+ |
| **MySQL Community Server** | 8.0 or 8.4 LTS | The database |
| **MySQL Workbench** | 8.0.36 or newer | Managing the database visually |
| **Git** | any recent | Source control |

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
node --version        # v20.x or v22.x
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
node --version        # v20.x or v22.x
npm --version
git --version
/usr/local/mysql/bin/mysql --version
```

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
- Choose `cs160_proj_proto/backend/schema.sql`.
- Click the **⚡ lightning-bolt** button (*Execute all*), or press **Ctrl+Shift+Enter** / **⌘⇧Enter**.

**2.3 Check the result**

The *Output* panel at the bottom should show green ticks and no red errors. The results grids should show:

| check_name | result |
|---|---|
| Products loaded: | 3 |
| MySQL version: | 8.0.x or 8.4.x |

and a grid of three products. In the left *Navigator* panel, click the **refresh icon** beside SCHEMAS — `ofs` now appears, containing `products`.

**What the script did:** created the `ofs` database, created a user `cs160team2` with password `team2_password` limited to that database, created the `products` table, and inserted three rows. Everyone on the team runs the same script, so the same `.env` works on all six machines — nobody needs to share a personal root password.

> ⚠️ Re-running `schema.sql` **drops and recreates** the database. That is intended for a spike. Do not develop this habit on the real project database.

---

## Part 3 — Set up the backend

### Windows (PowerShell)

```powershell
cd path\to\cs160_prj\spike\backend

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # see Troubleshooting #2 if blocked

python -m pip install --upgrade pip
pip install -r ../requirements.txt

copy .env.example .env
```

### macOS (Terminal)

```bash
cd path/to/cs160_prj/cs160_proj_proto/backend

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r ../requirements.txt

cp .env.example .env
```

Your prompt should now start with `(.venv)`. **The virtual environment must be active every time you work on the backend** — if you open a new terminal, activate it again.

The `.env` defaults match what `schema.sql` created, so no edits are needed unless you changed the user or password.

**Check 1 — the rules are correct:**

```bash
pytest -v
```

Expect **14 passed**. These tests need no database.

**Check 2 — the API runs and reaches MySQL:**

```bash
python app.py
```

You should see `Running on http://127.0.0.1:5001`. Leave it running and open a **second terminal**:

```bash
curl http://localhost:5001/api/health
curl http://localhost:5001/api/products
```

The second must include `"weight_python_type": "Decimal"`. If it says `float`, stop — the delivery-charge rule cannot be trusted and something is wrong with the driver.

> On Windows, `curl` in PowerShell is an alias for `Invoke-WebRequest` and formats output differently. Use `curl.exe http://localhost:5001/api/health`, or just open the URL in a browser.

---

## Part 4 — Set up the frontend

Open a **third terminal** (leave Flask running in the second).

```bash
cd path/to/cs160_prj/cs160_proj_proto/frontend
npm install
npm run dev
```

Vite prints `Local: http://localhost:5173/`. Open it.

Do **not** run `npm install` with `sudo` on macOS. If you get permission errors, see Troubleshooting #7.

---

## Part 5 — Verify the whole system

On `http://localhost:5173` you should see four checks. All should be green:

1. **React reaches Flask across origins** — CORS is configured correctly.
2. **Flask reaches MySQL and reads DECIMAL** — shows your MySQL version.
3. **Tailwind is compiling** — if the boxes are coloured and spaced, Tailwind works.
4. **Full chain** — set **6** apple bags and **20** lemons, press *Run cart check*.

That last one is the real test. 6 × 3.00 + 20 × 0.10 = **exactly 20.00 lb**, and the result must show:

```
Total weight   20.00 lb
Delivery       $10.00        ← not FREE
```

If it shows FREE at exactly 20.00 lb, the threshold comparison is using `<=` where it should use `<`.

Try **5** apple bags + **20** lemons (17.00 lb) and delivery should be FREE. Try **1** water pack (25.00 lb) — charged.

**Record your results** in the table at the end of `README.md` and put that in the Part II document.

---

## Running it again later

Three terminals, every time:

| Terminal | Windows | macOS |
|---|---|---|
| 1 — Flask | `cd spike\backend`<br>`.\.venv\Scripts\Activate.ps1`<br>`python app.py` | `cd cs160_proj_proto/backend`<br>`source .venv/bin/activate`<br>`python app.py` |
| 2 — Vite | `cd spike\frontend`<br>`npm run dev` | `cd cs160_proj_proto/frontend`<br>`npm run dev` |
| 3 — spare | for `pytest`, `curl`, git | same |

MySQL runs as a background service and starts with your computer, so you do not start it by hand.

---

## Troubleshooting

**1. macOS: "Address already in use" on port 5000**
You are running an older copy of this spike. Port 5000 is used by **AirPlay Receiver** on macOS Monterey and later. This spike uses 5001 for that reason. If you must free 5000: *System Settings → General → AirDrop & Handoff → AirPlay Receiver: Off*.

**2. Windows: "running scripts is disabled on this system"**
PowerShell blocks the venv activation script by default. Run this in the same window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

It applies to that window only and resets when you close it.

**3. `cryptography is required for sha256_password or caching_sha2_password`**
MySQL 8 uses an authentication plugin PyMySQL cannot speak on its own. `cryptography` is in `requirements.txt` for exactly this reason — you have a stale install. Re-run `pip install -r requirements.txt` with the venv active.

**4. `Access denied for user 'cs160team2'@'localhost'`**
`schema.sql` did not finish, or was run against a different MySQL instance. Re-run it in Workbench as root and confirm three products appear. Check `MYSQL_USER` and `MYSQL_PASSWORD` in `.env` match the script.

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
Another Vite server is running, probably from an earlier session. Vite will offer the next free port; accept it, then set `VITE_API_BASE` — or better, find the old terminal and stop it with Ctrl+C.

**12. Everything installed but `python` is not found (Windows)**
The "Add python.exe to PATH" box was missed during install. Re-run the installer, choose *Modify*, and tick it. Or use `py` instead of `python`.

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
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting, per the test plan |
| `react`, `react-dom` | The UI library |
| `vite`, `@vitejs/plugin-react` | Dev server and build tool |
| `tailwindcss`, `@tailwindcss/vite` | Styling; v4 is a Vite plugin with no config file |
