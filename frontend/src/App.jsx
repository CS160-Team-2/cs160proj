import { useEffect, useState } from 'react'

// With the Vite proxy off, this is a genuine cross-origin call to Flask.
const API = import.meta.env.VITE_API_BASE ?? 'http://localhost:5001'

function Check({ label, state, detail }) {
  const colour = {
    pass: 'bg-green-100 text-green-900 border-green-300',
    fail: 'bg-red-100 text-red-900 border-red-300',
    wait: 'bg-slate-100 text-slate-600 border-slate-300',
  }[state]
  const mark = { pass: '✓', fail: '✗', wait: '…' }[state]

  return (
    <div className={`flex gap-3 rounded border p-3 ${colour}`}>
      <span className="font-bold">{mark}</span>
      <div>
        <div className="font-medium">{label}</div>
        {detail && <div className="text-sm opacity-80">{detail}</div>}
      </div>
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState({ state: 'wait' })
  const [products, setProducts] = useState({ state: 'wait', rows: [] })
  const [qty, setQty] = useState({})
  const [cart, setCart] = useState(null)
  const [cartError, setCartError] = useState(null)

  // Seam 1 + 2: is Flask reachable from the browser across origins?
  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then(() => setHealth({ state: 'pass', detail: 'Flask reachable; CORS allows GET' }))
      .catch((e) => setHealth({ state: 'fail', detail: String(e) }))
  }, [])

  // Seam 3: can Flask reach MySQL, and does DECIMAL survive?
  useEffect(() => {
    fetch(`${API}/api/products`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error)
        setProducts({
          state: d.weight_python_type === 'Decimal' ? 'pass' : 'fail',
          rows: d.products,
          detail: `MySQL ${d.mysql_version} · weights arrive in Python as ${d.weight_python_type}`,
        })
      })
      .catch((e) => setProducts({ state: 'fail', rows: [], detail: String(e) }))
  }, [])

  // Seam 4: POST with a JSON body — triggers a CORS preflight, runs the
  // rule against values read from MySQL, and returns the result.
  async function runCartCheck() {
    setCartError(null)
    const lines = Object.entries(qty)
      .map(([product_id, quantity]) => ({ product_id: Number(product_id), quantity: Number(quantity) }))
      .filter((l) => l.quantity > 0)

    try {
      const res = await fetch(`${API}/api/cart-check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines }),
      })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error)
      setCart(data)
    } catch (e) {
      setCartError(String(e))
      setCart(null)
    }
  }

  const overThreshold = cart && !cart.free_delivery

  return (
    <div className="mx-auto max-w-2xl p-6 font-sans">
      <h1 className="text-2xl font-bold text-slate-800">OFS Feasibility Spike</h1>
      <p className="mt-1 text-slate-600">
        Proving React + Vite + Tailwind can talk to Flask, and Flask can talk to MySQL,
        without losing decimal precision.
      </p>

      <div className="mt-6 space-y-2">
        <Check label="1. React (Vite) reaches Flask across origins" state={health.state} detail={health.detail} />
        <Check label="2. Flask reaches MySQL and reads DECIMAL" state={products.state} detail={products.detail} />
        <Check
          label="3. Tailwind is compiling"
          state="pass"
          detail="If this box is coloured and spaced, Tailwind classes are being applied."
        />
      </div>

      <h2 className="mt-8 text-lg font-semibold text-slate-800">4. Full chain: browser → Flask → MySQL → rule</h2>
      <p className="text-sm text-slate-600">
        Set quantities and run the check. Try <strong>6 apple bags + 20 lemons</strong> — that is exactly
        20.00&nbsp;lb, which must be charged.
      </p>

      <div className="mt-3 space-y-2">
        {products.rows.map((p) => (
          <div key={p.product_id} className="flex items-center gap-3 rounded border border-slate-200 p-3">
            <input
              type="number"
              min="0"
              className="w-20 rounded border border-slate-300 px-2 py-1"
              value={qty[p.product_id] ?? 0}
              onChange={(e) => setQty({ ...qty, [p.product_id]: e.target.value })}
            />
            <div className="flex-1">
              <div className="font-medium text-slate-800">{p.name}</div>
              <div className="text-sm text-slate-500">
                ${p.price} · {p.unit_weight_lb} lb each
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={runCartCheck}
        className="mt-4 rounded bg-slate-800 px-4 py-2 font-medium text-white hover:bg-slate-700"
      >
        Run cart check (POST)
      </button>

      {cartError && (
        <div className="mt-4 rounded border border-red-300 bg-red-100 p-3 text-red-900">{cartError}</div>
      )}

      {cart && (
        <div className="mt-4 rounded border border-slate-300 bg-white p-4">
          <div className="flex justify-between">
            <span>Total weight</span>
            <span className="font-mono font-semibold">{cart.total_weight_lb} lb</span>
          </div>
          <div className="mt-2 h-2 w-full rounded bg-slate-200">
            <div
              className={`h-2 rounded ${overThreshold ? 'bg-amber-500' : 'bg-green-500'}`}
              style={{
                width: `${Math.min(100, (Number(cart.total_weight_lb) / Number(cart.threshold_lb)) * 100)}%`,
              }}
            />
          </div>
          <div className="mt-1 text-xs text-slate-500">threshold {cart.threshold_lb} lb</div>

          <div className="mt-4 flex justify-between">
            <span>Subtotal</span>
            <span className="font-mono">${cart.subtotal}</span>
          </div>
          <div className="flex justify-between">
            <span>Delivery</span>
            <span className={`font-mono ${overThreshold ? 'text-amber-700 font-semibold' : 'text-green-700'}`}>
              {cart.free_delivery ? 'FREE' : `$${cart.delivery_fee}`}
            </span>
          </div>
          <div className="mt-2 flex justify-between border-t border-slate-200 pt-2 font-semibold">
            <span>Order total</span>
            <span className="font-mono">${cart.order_total}</span>
          </div>
        </div>
      )}
    </div>
  )
}
