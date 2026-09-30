# Apache Feasibility Step

The last seam in the spike, and the one that is easiest to leave until November and then regret. Backlog task **T-25**; LLD §III research item 4.

## What this proves

In development there are two servers — Vite on 5173 and Flask on 5001 — and the browser sees two origins, which is why CORS is configured. **In production there is one origin.** Apache serves the built React files and forwards `/api` to Flask, so the browser never knows Flask exists on a separate port.

Three questions this answers, none of which can be answered by reading documentation:

| # | Question | Why it matters |
|---|---|---|
| 1 | Can Apache serve the Vite production build? | `npm run dev` and `npm run build` produce very different things. The build step has its own failure modes. |
| 2 | Can Apache reverse-proxy `/api` to Flask? | Needs `mod_proxy` and `mod_proxy_http` enabled. Not on by default in most installs. |
| 3 | Does the app work with **no CORS at all**? | If it does, CORS is proven to be a development-only concern. If it does not, something else is wrong and we want to know now. |

---

## Part 1 — Install Apache

### Windows 10 / 11

Windows has no built-in Apache. Easiest route is **XAMPP**:

1. Download from [apachefriends.org](https://www.apachefriends.org/) and install to `C:\xampp`.
2. Open the **XAMPP Control Panel**. You only need **Apache** — do *not* start XAMPP's MySQL, since you already installed MySQL properly in Part 1 of SETUP.md and two servers would fight over port 3306.
3. Config lives at `C:\xampp\apache\conf\httpd.conf`.

### macOS (Apple Silicon)

macOS ships Apache 2.4. Use it rather than installing another:

```bash
httpd -v                      # confirm it exists
sudo apachectl start
```

Config lives at `/etc/apache2/httpd.conf`. Visit `http://localhost` — "It works!" means Apache is running.

> Homebrew's `httpd` is an alternative if the built-in one gives trouble. It listens on 8080 by default and its config is at `/opt/homebrew/etc/httpd/httpd.conf`.

---

## Part 2 — Enable the required modules

Apache ships with these switched off. One command turns all three on (it backs up the file first):

```bash
sudo cp /etc/apache2/httpd.conf /etc/apache2/httpd.conf.backup

sudo sed -i '' \
  -e 's|^#\(LoadModule proxy_module .*\)|\1|' \
  -e 's|^#\(LoadModule proxy_http_module .*\)|\1|' \
  -e 's|^#\(LoadModule rewrite_module .*\)|\1|' \
  /etc/apache2/httpd.conf
```

Confirm:

```bash
grep -n "^LoadModule \(proxy\|proxy_http\|rewrite\)_module" /etc/apache2/httpd.conf
```

Three lines, no `#` in front.

`mod_proxy` and `mod_proxy_http` are both needed. Enabling only the first gives a confusing `500` with *"No protocol handler was valid"* in the error log.

## Part 3 — Build the frontend

```bash
cd cs160_proj_proto/frontend
VITE_API_BASE= npm run build          # macOS / Linux
```

```powershell
$env:VITE_API_BASE=""; npm run build   # Windows PowerShell
```

Setting `VITE_API_BASE` to an **empty string** is the important part. `App.jsx` reads:

```js
const API = import.meta.env.VITE_API_BASE ?? 'http://localhost:5001'
```

`??` only falls back on `null`/`undefined`, so an empty string is kept — and every call becomes a **relative** URL like `/api/health`. Relative means same-origin, which is exactly what we want behind Apache. Leave the variable unset and the built bundle would still try to reach `localhost:5001` directly, which defeats the whole exercise.

The output lands in `cs160_proj_proto/frontend/dist/`.

---

## Part 4 — Install the virtual host

Two things have to happen: the built files must go somewhere Apache can read, and `ofs.conf` must be copied into `/etc/apache2/` with its `__DIST__` placeholder filled in.

### 4a — Publish the build (macOS)

**Do not point `DocumentRoot` at `frontend/dist` inside `~/Desktop`.** Apache runs as the user `_www`, and to serve a file it must traverse every folder above it. On macOS your home folder is `drwx------` — owner only — and `~/Desktop` is additionally protected by TCC, Apple's privacy layer. `_www` is denied at the first step and never reaches `dist`, so every request returns **403 Forbidden**. `apachectl configtest` still says *Syntax OK*, because the syntax is fine; the failure only surfaces when a request actually arrives.

`chmod 755 ~` is the wrong fix — it exposes your whole home folder to every account on the machine, and TCC blocks Desktop regardless.

Instead, publish a copy into Apache's own document area:

```bash
cd ~/Desktop/SJSU_Fall_Semester_2026/CS160_SoftwareEngineering/cs160_prj/cs160_proj_proto
bash deploy/publish.sh
```

That copies `frontend/dist/` to `/Library/WebServer/Documents/ofs`, which is world-readable by design. The source of truth stays in your repo; what Apache serves is a deployed artifact — which is exactly how real deployment works. **Re-run `publish.sh` after every `npm run build`.**

### 4b — Install the config

```bash
sed "s|__DIST__|/Library/WebServer/Documents/ofs|g" deploy/ofs.conf \
  | sudo tee /etc/apache2/other/ofs.conf > /dev/null
```

`sed` swaps the placeholder, and `sudo tee` writes the result into Apache's config directory. Nothing else needs editing — `httpd.conf` already ends with `Include /private/etc/apache2/other/*.conf`, so Apache picks up any `.conf` dropped in there. The `Listen 8080` line is inside `ofs.conf` too, so even that is handled.

**Check it landed with the real path substituted:**

```bash
grep DocumentRoot /etc/apache2/other/ofs.conf
```

You should see your actual folder, not `__DIST__`.

Then:

```bash
sudo apachectl configtest      # expect "Syntax OK"
sudo apachectl restart
```

To change something later, edit `deploy/ofs.conf` in the project and re-run the same install command — that way the version in your repo stays the source of truth.

## Part 5 — Verify

Start Flask in its own terminal (Vite is **not** needed — Apache serves the built files):

```bash
cd cs160_proj_proto/backend
source .venv/bin/activate      # or .\.venv\Scripts\Activate.ps1
python app.py
```

Then open **`http://localhost:8080`**.

| Check | Expected |
|---|---|
| The page loads at `:8080` | Apache is serving the Vite build |
| Check 1 and 2 are green | Apache is proxying `/api` to Flask |
| Browser devtools → Network → `health` | Request URL is `http://localhost:8080/api/health` — **not** `:5001` |
| Browser devtools → Console | **No CORS messages at all** |
| Cart check still returns $10.00 at 20.00 lb | The full chain works through Apache |

**The CORS check is the interesting one.** Same origin means the browser never sends an `Origin` header and never runs a preflight. If the console is clean, you have proven CORS is a development-only concern.

### Prove the proxy is really working

Temporarily comment out the two `ProxyPass` lines and restart Apache. The page should still load but every check should fail with a 404 on `/api/health` — Apache looking for a *file* called `api/health` in `dist`. Uncomment, restart, and the checks go green again. That confirms the proxy, rather than something else, is doing the work.

---

## Record the result

| Check | Result | Notes |
|---|---|---|
| Apache serves the Vite production build | ☐ pass ☐ fail | Apache version: |
| `mod_proxy` + `mod_proxy_http` enabled | ☐ pass ☐ fail | |
| `/api` reverse-proxies to Flask | ☐ pass ☐ fail | |
| Works with **no CORS** (same origin) | ☐ pass ☐ fail | |
| SPA fallback — refresh on a sub-path works | ☐ pass ☐ fail | |

---

## Troubleshooting

**`500 Internal Server Error` on `/api`, log says "No protocol handler was valid"**
`mod_proxy_http` is not enabled. `mod_proxy` alone is not enough.

**`403 Forbidden` on the main page**
Apache runs as `_www` and cannot traverse a path under `~/Desktop` or `~/Documents`. Confirm with `tail -5 /var/log/apache2/ofs_error.log` — look for *"search permissions are missing on a component of the path"*. Fix: run `bash deploy/publish.sh` and point `DocumentRoot` at `/Library/WebServer/Documents/ofs` (Part 4a). Also check `<Directory>` matches `DocumentRoot` exactly.

**`502 Bad Gateway` or `503 Service Unavailable` on `/api`**
Flask is not running, or is on a different port. Confirm `python app.py` says `Running on http://127.0.0.1:5001`, and that `ProxyPass` points at 5001.

**Page loads but is unstyled**
Vite's build references assets by absolute path from the site root. If you deploy into a subdirectory rather than the document root, set `base` in `vite.config.js`. Serving from the root as above avoids this.

**Refreshing on a sub-path gives 404**
The `RewriteEngine` block is missing or `mod_rewrite` is not enabled.

**Windows / XAMPP**\nXAMPP has no `/other/` directory. Append the contents of `deploy/ofs.conf` to `C:\\xampp\\apache\\conf\\extra\\httpd-vhosts.conf`, replace `__DIST__` by hand with your `dist` path using forward slashes, and make sure `httpd.conf` has `Include conf/extra/httpd-vhosts.conf` uncommented.\n\n**macOS: `sudo apachectl restart` does nothing**
Another Apache (often Homebrew's) may be holding the port. `sudo lsof -i :8080` shows what is listening.

**Windows: Apache will not start from XAMPP**
Usually a port conflict. XAMPP's Control Panel *Netstat* button shows what has the port; Skype and IIS are common culprits on 80, which is another reason this config uses 8080.
