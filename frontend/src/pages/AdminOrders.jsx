import React, { useContext, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import { formatTime, statusLabels } from './Orders'

const isManager = (user) => user && user.role === 'manager'

// The two status changes a manager makes from this page. The steps in
// between (assigning to a trip, sending the trip out) happen on the
// delivery side, so for those the page only explains what comes next.
const actions = {
  awaiting_delivery: 'MARK READY FOR DELIVERY',
  delivered: 'CONFIRM DELIVERED',
}

const waitingOn = {
  assigned_to_trip: 'Next step: add this order to a delivery trip.',
  out_for_delivery: 'Next step: send its delivery trip out.',
}

const Row = ({ label, value }) => (
  <div className="flex justify-between text-sm">
    <p>{label}</p>
    <p>{value}</p>
  </div>
)

// Everything staff need about one order, loaded when the row is opened.
const OrderPanel = ({ orderId, currency, onChanged }) => {

  const [order, setOrder] = useState(null)
  const [payments, setPayments] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => {
    Promise.all([
      api(`/api/admin/orders/${orderId}`),
      api(`/api/admin/orders/${orderId}/payments`),
    ])
      .then(([detail, paid]) => {
        setOrder(detail.order)
        setPayments(paid.payments)
      })
      .catch((err) => setError(err.message))
  }

  useEffect(load, [orderId])

  const advance = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/admin/orders/${orderId}/status`, {
        method: 'PATCH',
        body: { status: order.next_status },
      })
      load()
      onChanged()
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  if (!order) {
    return <div className="pb-4">{error ? <p className="text-sm text-red-600">{error}</p> : <p className="text-sm text-gray-500">Loading...</p>}</div>
  }

  const { customer, address } = order

  return (
    <div className="pb-6 grid grid-cols-1 md:grid-cols-2 gap-6 text-gray-700">
      <div className="flex flex-col gap-4">
        <div>
          <p className="font-medium mb-1">Customer</p>
          <p className="text-sm">{customer.full_name}{customer.is_guest && <span className="text-gray-500"> (guest checkout)</span>}</p>
          <p className="text-sm text-gray-500">{customer.email}{customer.phone && ` · ${customer.phone}`}</p>
        </div>
        {address && (
          <div>
            <p className="font-medium mb-1">Deliver to</p>
            <p className="text-sm">{address.street}, {address.city}, {address.state} {address.zip_code}</p>
          </div>
        )}
        <div>
          <p className="font-medium mb-1">Items</p>
          {order.items.map((item) => (
            <Row key={item.product_id} label={`${item.quantity} × ${item.name}`} value={`${currency}${item.line_total}`} />
          ))}
          <div className="border-t mt-2 pt-2">
            <Row label="Total weight" value={`${order.total_weight_lb} lb`} />
            <Row label="Delivery fee" value={order.delivery_fee === '0.00' ? 'Free' : `${currency}${order.delivery_fee}`} />
            <Row label="Tax" value={`${currency}${order.tax}`} />
            <Row label="Total" value={`${currency}${order.grand_total}`} />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <div>
          <p className="font-medium mb-1">History</p>
          {order.history.map((step, i) => (
            <p key={i} className="text-sm">
              {statusLabels[step.to_status]}
              <span className="text-gray-500"> · {formatTime(step.changed_at)}{step.changed_by && ` · ${step.changed_by}`}</span>
            </p>
          ))}
        </div>
        {order.trip && (
          <p className="text-sm">On delivery trip #{order.trip.trip_id}, stop {order.trip.stop_sequence}</p>
        )}
        {order.unscheduled_reason && (
          <p className="text-sm text-red-600">Not scheduled: {order.unscheduled_reason}</p>
        )}
        <div>
          <p className="font-medium mb-1">Payments</p>
          {payments.length === 0 && <p className="text-sm text-gray-500">No payment attempts.</p>}
          {payments.map((p) => (
            <p key={p.transaction_id} className="text-sm">
              {currency}{p.amount} · {p.status}{p.card_last4 && ` · card ending ${p.card_last4}`}
              {p.failure_reason && <span className="text-red-600"> · {p.failure_reason}</span>}
            </p>
          ))}
        </div>
        <div>
          {actions[order.next_status] && (
            <button onClick={advance} disabled={busy} className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400">
              {actions[order.next_status]}
            </button>
          )}
          {waitingOn[order.next_status] && <p className="text-sm text-gray-500">{waitingOn[order.next_status]}</p>}
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    </div>
  )
}

// /admin/orders: managers see every order, filter by status and date,
// and move an order along when it is packed or delivered
const AdminOrders = () => {

  const { user, currency } = useContext(StoreContext)
  const [orders, setOrders] = useState(null)
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [openId, setOpenId] = useState(null)
  const [error, setError] = useState('')

  const load = () => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    api(`/api/admin/orders?${params}`)
      .then((data) => {
        setOrders(data.orders)
        setError('')
      })
      .catch((err) => setError(err.message))
  }

  useEffect(() => {
    if (isManager(user)) load()
  }, [user, status, from, to])

  if (user === undefined) return null
  if (!isManager(user)) return <Navigate to="/login" replace />

  return (
    <div className="border-t-2 pt-14">
      <div className="text-2xl mb-6">
        <TextContent text1={'ORDER'} text2={'MONITOR'} />
      </div>

      <div className="flex flex-wrap gap-3 mb-6">
        <select className="border px-3 py-2" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {Object.entries(statusLabels).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          From
          <input className="border px-3 py-2" type="date" aria-label="From date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          To
          <input className="border px-3 py-2" type="date" aria-label="To date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {orders && orders.length === 0 && <p className="text-gray-600">No orders match.</p>}
      {orders && orders.map((order) => (
        <div key={order.order_id} className="border-t border-b">
          <button
            onClick={() => setOpenId(openId === order.order_id ? null : order.order_id)}
            aria-expanded={openId === order.order_id}
            className="w-full py-4 text-left text-gray-700 flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer"
          >
            <div>
              <p className="font-medium">{order.order_number}</p>
              <p className="text-sm text-gray-500">{order.customer_name} · {formatTime(order.placed_at)} · {order.item_count} items</p>
            </div>
            <p className="text-sm">{currency}{order.grand_total} · {order.total_weight_lb} lb</p>
            <p className="text-sm">
              {statusLabels[order.status]}
              {order.trip_id && <span className="text-gray-500"> · trip #{order.trip_id}</span>}
              {order.unscheduled_reason && <span className="ml-2 text-red-600">NEEDS ATTENTION</span>}
            </p>
          </button>
          {openId === order.order_id && (
            <OrderPanel orderId={order.order_id} currency={currency} onChanged={load} />
          )}
        </div>
      ))}
    </div>
  )
}

export default AdminOrders
