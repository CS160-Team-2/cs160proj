# OFS Feasibility Spike

**Purpose:** prove the chosen stack works together before Part III starts. This is a *spike*, not a first draft of the product — none of this code is meant to survive into the real system. It exists to answer four questions and then be thrown away.

Covers LLD §III research items 2 and 4, and supports backlog tasks T-03, T-11 and T-25.

---

## What it proves

A spike should target the **seams**, not the features. Each piece of the stack is well documented and almost certainly works on its own; what breaks is where two pieces meet. The four seams:

| # | Seam | Why it is the risk |
|---|---|---|
| 1 | React (Vite, port 5173) → Flask (port 5001) | Different ports are different origins to the browser. Without CORS configured, every call from React fails even though the API works perfectly in Postman. This is the first thing that breaks for a team moving from Node to Flask. |
| 2 | POST with a JSON body | A JSON POST triggers a CORS **preflight** (an `OPTIONS` request). A setup that handles GET fine can still fail here — so the spike deliberately includes one. |
| 3 | Flask → MySQL | Driver installs, credentials, and whether `DECIMAL` columns come back as Python `Decimal` or as `float`. |
| 4 | Decimal precision end to end | The whole 20 lb rule depends on `0.10 × 10` being exactly `1.00`. In floating point it is `0.9999999999999999`, and a cart meant to sit on the threshold lands on the wrong side of the charge. |

Seam 4 is the one worth the most attention. It is invisible until it costs a customer $10.

---

## Files

```
cs160_proj_proto/
├── backend/
│   ├── schema.sql        3 products, chosen to exercise the 20 lb boundary
│   ├── db.py             MySQL connection (PyMySQL)
│   ├── rules.py          Features 5.2 and 5.3 as pure functions
│   ├── app.py            Flask API — 3 endpoints, one per seam
│   ├── test_rules.py     Pytest, from the test plan's equivalence partitions
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json
    ├── vite.config.js    Tailwind v4 plugin; proxy deliberately off
    ├── index.html
    └── src/
        ├── main.jsx
        ├── index.css     Tailwind v4 — one @import, no config file
        └── App.jsx       Shows pass/fail for each seam
```

---

## Running it

**Full step-by-step setup for Windows and macOS, including MySQL Workbench, is in [SETUP.md](SETUP.md).** The short version follows.

**1. Database**

Open `backend/schema.sql` in MySQL Workbench (**File → Open SQL Script**) and run it with the ⚡ button. It creates the `ofs` database, an `cs160team2` user, and three products.

Expect three rows printed back.

**2. Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults already match schema.sql
python app.py
```

Flask serves on `http://localhost:5001`. Check it directly first:

```bash
curl http://localhost:5001/api/health
curl http://localhost:5001/api/products
```

The second should report your MySQL version and `"weight_python_type": "Decimal"`.

**3. Tests**

```bash
pytest -v
```

14 tests, all passing. The logic has been verified — if these fail, something is wrong with the environment rather than the code.

**4. Frontend**

```bash
cd ../frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Four checks appear. Set **6** apple bags and **20** lemons and press *Run cart check* — that is exactly 20.00 lb and must show a **$10.00** charge, not FREE.

---

## Results to record

Fill this in and put it in the Part II document as the outcome of the prototyping task.

| Seam | Result | Notes |
|---|---|---|
| 1. React → Flask, GET across origins | ☐ pass ☐ fail | |
| 2. JSON POST (CORS preflight) | ☐ pass ☐ fail | |
| 3. Flask → MySQL, DECIMAL preserved | ☐ pass ☐ fail | MySQL version: |
| 4. `0.10 × 10 == 1.00` end to end | ☐ pass ☐ fail | |
| 5. Tailwind compiles under Vite | ☐ pass ☐ fail | Tailwind version: |
| 6. Pytest runs | ☐ pass ☐ fail | |

---

## Things to watch for

**Tailwind v3 vs v4.** Tailwind changed setup substantially in v4. This spike uses **v4**, which is a Vite plugin — one `@import "tailwindcss";` in the CSS, no `tailwind.config.js`, no `postcss.config.js`. Most tutorials still show v3, which needs both config files and three `@tailwind` directives. If `npm install tailwindcss` gives your team v3, follow the comments in `vite.config.js` and `index.css`. **Decide which version as a team before anyone builds a screen** — mixing the two setups wastes an afternoon.

**CORS vs the Vite proxy.** There are two ways to let React reach Flask in development: configure CORS on Flask (what this spike does), or use Vite's dev proxy so the browser only ever sees one origin. The proxy config is in `vite.config.js`, commented out. The proxy is simpler for development but hides the problem — in production Apache serves both, so CORS behaviour needs to be understood either way. Worth ten minutes of team discussion.

**Decimal does not survive JSON.** JSON has no decimal type, so `app.py` sends money and weight as **strings**. The browser only displays them; it never does arithmetic on them. Keep it that way — the moment React does `Number(weight) + Number(weight)`, the precision guarantee is gone. This is a rule worth writing into the team's coding standards now.

**One connection per request.** `db.py` opens a connection per request, which is fine at spike scale and wrong for the real system. Connection pooling is a T-02 / T-25 concern, not a spike concern.

---

## Not covered here

**Google Maps** (LLD §III item 1, backlog T-16) is a separate spike owned by whoever takes delivery planning. It needs an API key and proves a different thing: that `duration_in_traffic` is returned when `departure_time` is set to a future time, and what an 11 × 11 distance matrix costs against the free tier. Do not fold it into this one — it fails for different reasons.

**Payment sandbox** (LLD §III item 3, backlog T-12) likewise. A stub behind the same interface is acceptable for the demo, so this is lower risk than it looks.

**Apache deployment** (LLD §III item 4, backlog T-25). This spike runs the Vite dev server and Flask's development server. Neither is what ships. Proving Apache can serve the built React bundle and reverse-proxy `/api` to Flask is a separate afternoon, and worth doing early rather than in November.
