import React, { useContext, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import ManagerPagination from '../components/ManagerPagination'
import useManagerList from '../useManagerList'
import { loginUrl } from '../redirects'

const statusLabels = {
  placed: 'Order placed',
  awaiting_delivery: 'Awaiting delivery',
  assigned_to_trip: 'Assigned to a trip',
  out_for_delivery: 'Out for delivery',
  delivered: 'Delivered',
}

// Formats a date and time for the list.
const formatTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

// One order the employee can open to see what is in it; read-only, with no contact or payment details.
const OrderRow = ({ order, currency }) => {

  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let current = true
    api(`/api/staff/orders/${order.order_id}`)
      .then((data) => { if (current) { setDetail(data.order); setError('') } })
      .catch((err) => { if (current) setError(err.message) })
    return () => { current = false }
  }, [open, order.order_id, order.status])

  return (
    <div className="py-4 border-t border-b text-gray-700">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full text-left flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer">
        <span className="min-w-0 break-words">
          <span className="block font-medium">{order.order_number}</span>
          <span className="block text-sm text-gray-500">{order.customer_name} · {formatTime(order.placed_at)} · {order.item_count} items · {order.total_weight_lb} lb · {currency}{order.grand_total}</span>
        </span>
        <span className="text-sm">{statusLabels[order.status]}{order.trip_id ? ` · trip #${order.trip_id}` : ''}</span>
      </button>
      {order.unscheduled_reason && <p className="mt-1 text-sm text-red-600">Not scheduled: {order.unscheduled_reason}</p>}
      {open && (
        <div className="mt-4 grid sm:grid-cols-2 gap-6 text-sm">
          {error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}
          {!detail && !error && <p role="status" className="sm:col-span-2 text-gray-500">Loading the order...</p>}
          {detail && (
            <>
              <div className="flex flex-col gap-1">
                <p className="font-medium">Items to pick</p>
                {detail.items.map((item) => (
                  <p key={item.product_id} className="text-gray-600">{item.quantity} × {item.name} · {item.unit_weight_lb} lb each · {currency}{item.line_total}</p>
                ))}
                <p className="text-gray-500 mt-1">Subtotal {currency}{detail.subtotal} · Tax {currency}{detail.tax} · Delivery {currency}{detail.delivery_fee} · Total {currency}{detail.grand_total}</p>
              </div>
              <div className="flex flex-col gap-1">
                <p className="font-medium">Progress</p>
                {detail.history.map((step, index) => (
                  <p key={index} className="text-gray-600">{statusLabels[step.status]} · {formatTime(step.at)}</p>
                ))}
                {detail.trip && <p className="text-gray-500 mt-1">On trip #{detail.trip.trip_id}, stop {detail.trip.stop_sequence ?? '-'}. <Link to="/delivery" className="text-green-700 underline">See the delivery tracking</Link></p>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// /staff/orders: employees and managers see every order and its status, read-only.
const EmployeeOrders = () => {

  const { user, currency } = useContext(StoreContext)
  const staff = user && ['employee', 'manager'].includes(user.role)
  const [status, setStatus] = useState('')
  const [draft, setDraft] = useState({ q: '', from: '', to: '' })
  const [applied, setApplied] = useState({ q: '', from: '', to: '' })
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)

  const params = new URLSearchParams({ page, per_page: size })
  if (status) params.set('status', status)
  for (const key of ['q', 'from', 'to']) if (applied[key]) params.set(key, applied[key])
  const { data, error, loading, refresh } = useManagerList(staff ? `/api/staff/orders?${params}` : null)

  if (user === undefined) return <p role="status">Checking your account...</p>
  if (!user) return <Navigate to={loginUrl('/staff/orders')} replace />
  if (!staff) return <Navigate to="/orders" replace />

  const counts = data?.status_counts
  const orders = data?.orders
  const chip = (active) => `border text-sm px-4 py-1 ${active ? 'border-green-600 bg-green-600 text-white' : 'border-gray-300 text-gray-700'}`
  const choose = (value) => { setStatus(value); setPage(1) }
  const apply = (event) => { event.preventDefault(); setApplied(draft); setPage(1) }
  const clear = () => { setDraft({ q: '', from: '', to: '' }); setApplied({ q: '', from: '', to: '' }); setStatus(''); setPage(1) }

  return (
    <div className="border-t-2 pt-14 flex flex-col gap-4">
      <div className="text-2xl"><TextContent text1="CUSTOMER" text2="ORDERS" /></div>
      <div className="flex flex-wrap gap-4 text-sm">
        <Link to="/inventory" className="text-green-700 underline">Inventory</Link>
        <Link to="/delivery" className="text-green-700 underline">Delivery tracking</Link>
      </div>
      <p className="text-sm text-gray-600">Every order and where it is. You can look but not change: your manager marks orders ready and sends them out.</p>

      <form onSubmit={apply} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-gray-700">Search orders
          <input type="search" value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} placeholder="Order number or customer name" className="border border-gray-300 px-3 py-2" />
        </label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-gray-700">From date<input type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} className="border border-gray-300 px-3 py-2" /></label>
          <label className="flex flex-col gap-1 text-sm text-gray-700">To date<input type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} className="border border-gray-300 px-3 py-2" /></label>
          <button type="submit" className="bg-green-600 px-4 py-2 text-sm text-white">Apply filters</button>
          <button type="button" onClick={clear} className="px-3 py-2 text-sm text-green-700 underline">Clear filters</button>
          <button type="button" onClick={refresh} className="px-3 py-2 text-sm text-green-700 underline">Refresh orders</button>
        </div>
      </form>

      {error && <p role="alert" className="text-sm text-red-700">Could not refresh orders: {error}{orders && ' Showing the last successful results.'}</p>}
      {loading && !orders && <p role="status" className="text-sm text-gray-500">Loading orders...</p>}
      {orders && (
        <>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => choose('')} aria-pressed={status === ''} className={chip(status === '')}>All ({counts ? Object.values(counts).reduce((a, b) => a + b, 0) : orders.length})</button>
            {Object.keys(statusLabels).map((key) => (
              <button key={key} onClick={() => choose(key)} aria-pressed={status === key} className={chip(status === key)}>{statusLabels[key]} ({counts?.[key] ?? 0})</button>
            ))}
          </div>
          {orders.length === 0 && <p className="text-gray-600">No orders here.</p>}
          {orders.map((order) => <OrderRow key={order.order_id} order={order} currency={currency} />)}
          <ManagerPagination value={data.pagination} loading={loading} onPage={setPage} onSize={(value) => { setSize(value); setPage(1) }} />
        </>
      )}
    </div>
  )
}

export default EmployeeOrders
