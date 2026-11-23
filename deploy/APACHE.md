# Running OFS behind Apache

The assignment recommends Apache as the web server. In production Apache serves the built React site and forwards `/api` to Flask, so the browser sees **one address** and no CORS is involved. (In development there are two servers, Vite on 5173 and Flask on 5001, which is why CORS is configured.)

| What | Where |
|---|---|
| Apache configuration | [`ofs.conf`](ofs.conf) |
| Copies the build to a folder Apache can read (macOS) | [`publish.sh`](publish.sh) |
| Address of the site | `http://localhost:8080` |
| Flask (behind Apache) | `http://127.0.0.1:5001` |

Run every command from the repository root unless it says otherwise. The rest of the setup (MySQL, Python, the `.env` file) is in [SETUP.md](../SETUP.md).

---

## Part 1 — Install Apache

### Windows 10 / 11

Windows has no built-in Apache. The easiest route is **XAMPP**:

1. Download it from [apachefriends.org](https://www.apachefriends.org/) and install to `C:\xampp`.
2. Open the **XAMPP Control Panel** and start only **Apache**. Do *not* start XAMPP's MySQL: you already installed MySQL in SETUP.md Part 1, and two servers would fight over port 3306.
3. The config is at `C:\xampp\apache\conf\httpd.conf`.

### macOS

macOS ships Apache 2.4. Use it rather than installing another:

```bash
httpd -v                      # confirm it exists
sudo apachectl start
```

The config is at `/etc/apache2/httpd.conf`. Visit `http://localhost`: "It works!" means Apache is running.

Homebrew's `httpd` also works. It listens on 8080 by default and its config is at `/opt/homebrew/etc/httpd/httpd.conf`.

---

## Part 2 — Enable the required modules

Apache ships with three modules switched off. This turns them on (and backs up the file first):

```bash
sudo cp /etc/apache2/httpd.conf /etc/apache2/httpd.conf.backup

sudo sed -i '' \
  -e 's|^#\(LoadModule proxy_module .*\)|\1|' \
  -e 's|^#\(LoadModule proxy_http_module .*\)|\1|' \
  -e 's|^#\(LoadModule rewrite_module .*\)|\1|' \
  /etc/apache2/httpd.conf
```

Confirm. You should see three lines with no `#` in front:

```bash
grep -n "^LoadModule \(proxy\|proxy_http\|rewrite\)_module" /etc/apache2/httpd.conf
```

`mod_proxy` and `mod_proxy_http` are both needed. With only the first, requests to `/api` fail with a `500` and *"No protocol handler was valid"* in the error log.

On Windows/XAMPP, open `httpd.conf` and remove the `#` in front of the same three `LoadModule` lines.

---

## Part 3 — Build the frontend

The site must call its own address, so build it with an **empty** API base:

```bash
cd frontend
VITE_API_BASE= npm run build          # macOS / Linux
```

```powershell
$env:VITE_API_BASE=""; npm run build   # Windows PowerShell
```

`frontend/src/api.js` reads `import.meta.env.VITE_API_BASE ?? 'http://localhost:5001'`. The `??` only falls back when the variable is missing, so an empty string is kept and every call becomes a relative address such as `/api/health`. If the variable is left unset, the build would still try to reach `localhost:5001` directly and the whole point is lost.

The output is `frontend/dist/`.

---

## Part 4 — Install the virtual host

Two things have to happen: the built files must go somewhere Apache can read, and `ofs.conf` must be installed with its `__DIST__` placeholder filled in.

### 4a — Publish the build (macOS)

**Do not point `DocumentRoot` at `frontend/dist` inside `~/Desktop`.** Apache runs as the user `_www` and must be able to open every folder above a file to serve it. On macOS your home folder is owner-only and `~/Desktop` is additionally protected, so Apache answers `403 Forbidden` for every request even though `apachectl configtest` says `Syntax OK`. Loosening your home folder's permissions is the wrong fix: it exposes it to every account on the machine.

Instead publish a copy into Apache's own document folder:

```bash
bash deploy/publish.sh
```

This copies `frontend/dist/` to `/Library/WebServer/Documents/ofs` (it asks for your administrator password). Your repository stays the source of truth and Apache serves a deployed copy. **Run it again after every `npm run build`.**

### 4b — Install the config

```bash
sed "s|__DIST__|/Library/WebServer/Documents/ofs|g" deploy/ofs.conf \
  | sudo tee /etc/apache2/other/ofs.conf > /dev/null
```

`sed` fills in the placeholder and `sudo tee` writes the result where Apache loads it: `httpd.conf` already includes every `.conf` in `/etc/apache2/other/`, and `ofs.conf` declares its own `Listen 8080`, so nothing else needs editing. Check that the real path was written:

```bash
grep DocumentRoot /etc/apache2/other/ofs.conf     # your folder, not __DIST__
sudo apachectl configtest                         # expect "Syntax OK"
sudo apachectl restart
```

To change something later, edit `deploy/ofs.conf` and run the same install command again.

**Windows/XAMPP** has no `other` folder. Append the contents of `deploy/ofs.conf` to `C:\xampp\apache\conf\extra\httpd-vhosts.conf`, replace `__DIST__` by hand with your `dist` folder using forward slashes (`C:/.../frontend/dist`), and make sure `httpd.conf` includes `conf/extra/httpd-vhosts.conf`. Restart Apache from the Control Panel.

---

## Part 5 — Run and verify

Start Flask in its own terminal. Vite is **not** needed; Apache serves the built files:

```bash
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
cd backend
python app.py
```

In `backend/.env` set `TRUSTED_PROXIES=1` so the sign-in rate limits see each visitor instead of Apache. Then open **`http://localhost:8080`**.

| Check | Expected |
|---|---|
| The page loads at port 8080 | Apache is serving the build |
| `curl http://localhost:8080/api/health` | `"ok": true` and `"database": "up"`: Apache is forwarding to Flask |
| `curl http://localhost:8080/api/products` | 39 products |
| Reload the browser on `/products` or `/orders` | The page comes back (not a 404): the rewrite rule works |
| Browser devtools, Network, any `/api/...` request | The address is `localhost:8080`, never `:5001` |
| Browser devtools, Console | No CORS messages at all |
| Sign in as `customer@ofs.test`, add apples, open checkout | Works through the single address |

To prove the proxy is really doing the work, comment out the two `ProxyPass` lines and restart Apache: the page still loads but `/api/health` fails with a 404. Put the lines back and restart.

### Result of the check (2026-11-23)

| Check | Result | Notes |
|---|---|---|
| Apache serves the production build | pass | Apache 2.4.66 (the version built into macOS), run as a normal user on port 8081 with this `ofs.conf` |
| `mod_proxy`, `mod_proxy_http` and `mod_rewrite` enabled | pass | `apachectl`'s own syntax check says `Syntax OK` |
| `/api` is forwarded to Flask | pass | `/api/health` answered, 39 products, Flask's own headers and its 401 for a signed-out request came through |
| Works with no CORS (same origin) | pass | A real browser signed in, added to the cart and opened checkout; every `/api` request used the one Apache address |
| Reloading a sub-page works | pass | `/products` and an unknown address both return the app |
| Not checked | | The system install with `publish.sh` (it needs administrator rights), and Windows/XAMPP |

### Notes for a real server

- `python app.py` (Flask's development server) is fine behind Apache for a class demonstration, but it handles one request at a time and is not meant for production. A production-grade option is Waitress, which is pure Python and runs the same on Windows and macOS (Gunicorn does not run on Windows).
- For HTTPS follow the steps under *Security and HTTPS* in [SETUP.md](../SETUP.md): your own `SECRET_KEY`, `SESSION_COOKIE_SECURE=1` and `TRUSTED_PROXIES=1`.

---

## Troubleshooting

**`500 Internal Server Error` on `/api`, log says "No protocol handler was valid"**
`mod_proxy_http` is not enabled. `mod_proxy` alone is not enough.

**`403 Forbidden` on the main page**
Apache cannot read a path under `~/Desktop` or `~/Documents`. Confirm with `tail -5 /var/log/apache2/ofs_error.log`: look for *"search permissions are missing on a component of the path"*. Fix: run `bash deploy/publish.sh` and point `DocumentRoot` at `/Library/WebServer/Documents/ofs`.

**`502 Bad Gateway` or `503 Service Unavailable` on `/api`**
Flask is not running or is on another port. Confirm `python app.py` says `Running on http://127.0.0.1:5001`, and that `ProxyPass` points at 5001.

**The page loads but is unstyled**
Vite's build refers to assets from the site root. If you deploy into a sub-folder instead of the document root, set `base` in `vite.config.js`. Serving from the root as above avoids this.

**Refreshing on a sub-page gives a 404**
The `RewriteEngine` block is missing or `mod_rewrite` is not enabled.

**`AH00023: Couldn't create the proxy mutex` when starting Apache as a normal user**
Only happens when Apache is run without administrator rights (for example for a quick test). Add `Mutex file:/some/writable/folder default` to your own `httpd.conf`. A normal `sudo apachectl` install does not need it.

**Port 8080 is already in use**
Another Apache (often Homebrew's) may be holding it. `sudo lsof -i :8080` shows what is listening.

**Windows: Apache will not start from XAMPP**
Usually a port conflict. The Control Panel's *Netstat* button shows what has the port; Skype and IIS are common culprits on port 80, which is one reason this config uses 8080.
