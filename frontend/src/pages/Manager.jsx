import React, { useContext, useEffect, useRef, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import DeliveryOverview from '../components/DeliveryOverview'
import DeliveryMap from '../components/DeliveryMap'
import ArrivalEstimate from '../components/ArrivalEstimate'
import ManagerLayout from '../components/ManagerLayout'

const statusLabels = {
  placed: 'Order placed',
  awaiting_delivery: 'Awaiting delivery',
  assigned_to_trip: 'Assigned to a trip',
  out_for_delivery: 'Out for delivery',
  delivered: 'Delivered',
}

const tripLabels = {
  planned: 'Planned',
  out_for_delivery: 'Out for delivery',
  completed: 'Completed',
}

const providerName = (provider) => ({
  google: 'Google Routes',
  mapbox: 'Mapbox',
  fake: 'the offline demo provider',
}[provider] || 'the mapping provider')

const formatTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

const waited = (minutes) => (minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`)

const round = (number) => Math.round(number * 100) / 100

// Managers only; everyone else is sent somewhere they are allowed to be.
const useManager = () => {
  const { user } = useContext(StoreContext)
  if (user === undefined) return { ready: false }
  if (!user) return { ready: false, redirect: '/login' }
  if (user.role !== 'manager') return { ready: false, redirect: user.role === 'employee' ? '/inventory' : '/' }
  return { ready: true }
}

const Section = ({ text1, text2, children }) => (
  <div className="flex flex-col gap-4 mb-12">
    <div className="text-xl sm:text-2xl">
      <TextContent text1={text1} text2={text2} />
    </div>
    {children}
  </div>
)

// A used-versus-limit bar, in the same style as the order progress bars
const Meter = ({ label, used, limit, unit = '' }) => {
  const over = used > Number(limit)
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-sm text-gray-600">
        <p>{label}</p>
        <p className={over ? 'text-red-600' : ''}>{round(used)} of {Number(limit)}{unit}</p>
      </div>
      <div className="h-2 bg-gray-200">
        <div className={`h-2 ${over ? 'bg-red-600' : 'bg-green-600'}`} style={{ width: `${Math.min(100, (used / Number(limit)) * 100)}%` }} />
      </div>
    </div>
  )
}

// =====================================================================
// /manager: every customer order
// =====================================================================

const paymentLabels = { approved: 'Approved', declined: 'Declined', refunded: 'Refunded' }

const OrderPayments = ({ orderId, currency }) => {
  const [payments, setPayments] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let current = true
    let sequence = 0
    const load = async () => {
      const request = ++sequence
      try {
        const data = await api(`/api/admin/orders/${orderId}/payments`)
        if (current && request === sequence) { setPayments(data.payments); setError('') }
      } catch (err) { if (current && request === sequence) setError(err.message) }
    }
    load()
    const timer = setInterval(load, 15000)
    return () => { current = false; clearInterval(timer) }
  }, [orderId, retry])

  return (
    <section className="sm:col-span-2 min-w-0 flex flex-col gap-2" aria-label="Order payments">
      <h3 className="font-medium">Payments</h3>
      {error && <div role="alert" className="text-red-700">Could not load payments: {error}{payments && ' Showing the last successful update.'} <button type="button" onClick={() => setRetry((value) => value + 1)} className="underline">Retry payments</button></div>}
      {payments === null && !error && <p role="status" className="text-gray-500">Loading payments...</p>}
      {payments?.length === 0 && <p className="text-gray-500">No payment attempts are recorded for this order.</p>}
      {payments?.length > 0 && <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Payment attempts for this order</caption>
          <thead><tr>{['Time', 'Transaction ID', 'Gateway reference', 'Status', 'Amount', 'Card ending', 'Reason'].map((label) => <th key={label} scope="col" className="border-b p-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>{payments.map((payment) => <tr key={payment.transaction_id}>
            <td className="border-b p-2">{formatTime(payment.created_at)}</td>
            <td className="border-b p-2">{payment.transaction_id}</td>
            <td className="border-b p-2 break-all">{payment.gateway_ref || 'Not recorded'}</td>
            <td className={`border-b p-2 ${payment.status === 'declined' ? 'text-red-700' : payment.status === 'approved' ? 'text-green-700' : 'text-gray-700'}`}>{paymentLabels[payment.status] || payment.status}</td>
            <td className="border-b p-2 whitespace-nowrap">{currency}{payment.amount}</td>
            <td className="border-b p-2">{payment.card_last4 || 'Not recorded'}</td>
            <td className="border-b p-2 break-words">{payment.failure_reason || 'None'}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>
  )
}

const OrderRow = ({ order, currency, onChanged }) => {

  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [tracking, setTracking] = useState(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!open) return
    let current = true
    const load = () => Promise.all([
      api(`/api/admin/orders/${order.order_id}`),
      api(`/api/admin/orders/${order.order_id}/tracking`),
    ]).then(([data, track]) => {
      if (current) { setDetail(data.order); setTracking(track) }
    }).catch((err) => { if (current) setMessage(err.message) })
    load()
    const timer = setInterval(load, 15000)
    return () => { current = false; clearInterval(timer) }
  }, [open, order.order_id, order.status])

  const setStatus = async (status) => {
    try {
      await api(`/api/admin/orders/${order.order_id}/status`, { method: 'PATCH', body: { status } })
      setMessage('')
      onChanged()
    } catch (err) {
      setMessage(err.message)
    }
  }

  // Only these two steps are the manager's own; the others happen on a trip.
  const action = {
    placed: { label: 'MARK READY FOR DELIVERY', status: 'awaiting_delivery' },
    out_for_delivery: { label: 'CONFIRM DELIVERED', status: 'delivered' },
  }[order.status]

  return (
    <div className="py-4 border-t border-b text-gray-700">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="text-left cursor-pointer">
          <p className="font-medium">{order.order_number}</p>
          <p className="text-sm text-gray-500">
            {order.customer_name} · {formatTime(order.placed_at)} · {order.item_count} items · {order.total_weight_lb} lb · {currency}{order.grand_total}
          </p>
          {order.customer_email && <p className="text-xs text-gray-500 break-all">{order.customer_email}{order.is_guest ? ' · Guest checkout' : ''}</p>}
        </button>
        <div className="sm:text-right">
          <p className="text-sm">{statusLabels[order.status]}</p>
          {order.trip_id && <p className="text-sm text-gray-500">Trip #{order.trip_id}</p>}
        </div>
        <div>
          {action && (
            <button onClick={() => setStatus(action.status)} className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400">{action.label}</button>
          )}
          {order.status === 'awaiting_delivery' && (
            <Link to="/manager/delivery" className="text-sm text-green-600 underline">Add to a trip</Link>
          )}
          {order.status === 'assigned_to_trip' && (
            <Link to="/manager/delivery" className="text-sm text-green-600 underline">Dispatch its trip</Link>
          )}
        </div>
      </div>
      {order.unscheduled_reason && <p className="mt-1 text-sm text-red-600">Not scheduled: {order.unscheduled_reason}</p>}
      {message && <p className="mt-1 text-sm text-red-600">{message}</p>}

      {open && detail && (
        <div className="mt-4 grid sm:grid-cols-2 gap-6 text-sm">
          <div className="flex flex-col gap-1">
            <p className="font-medium">Items</p>
            {detail.items.map((item) => (
              <p key={item.product_id} className="text-gray-600">
                {item.quantity} × {item.name} · {item.unit_weight_lb} lb each · {currency}{item.line_total}
              </p>
            ))}
            <p className="text-gray-500 mt-1">Subtotal {currency}{detail.subtotal} · Tax {currency}{detail.tax} · Delivery {currency}{detail.delivery_fee}</p>
          </div>
          <div className="flex flex-col gap-1">
            <p className="font-medium">Customer and address</p>
            <p className="text-gray-600">{detail.customer.full_name}{detail.customer.is_guest ? ' (guest checkout)' : ''} · {detail.customer.email}{detail.customer.phone ? ` · ${detail.customer.phone}` : ''}</p>
            <p className="text-gray-600">{detail.address.street}, {detail.address.city}, {detail.address.state} {detail.address.zip_code}</p>
            <p className="text-gray-500">{detail.payment ? `Paid with a card ending ${detail.payment.card_last4}` : 'No approved payment on record'}</p>
          </div>
          <div className="sm:col-span-2 flex flex-col gap-1">
            <ArrivalEstimate value={tracking?.estimated_arrival} />
            <DeliveryMap trackingMap={tracking?.map} status={order.status} />
          </div>
          <OrderPayments orderId={order.order_id} currency={currency} />
          <div className="sm:col-span-2 flex flex-col gap-1">
            <p className="font-medium">History</p>
            {detail.history.map((step, index) => (
              <p key={index} className="text-gray-600">
                {formatTime(step.changed_at)} · {statusLabels[step.to_status]}{step.changed_by ? ` by ${step.changed_by}` : ''}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export const ManagerOrders = () => {

  const { currency } = useContext(StoreContext)
  const { ready, redirect } = useManager()
  const [orders, setOrders] = useState(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [draft, setDraft] = useState({ q: '', from: '', to: '' })
  const [applied, setApplied] = useState({ q: '', from: '', to: '' })
  const [filterError, setFilterError] = useState('')
  const [loading, setLoading] = useState(false)
  const reload = useRef(null)

  useEffect(() => {
    if (!ready) return
    let current = true
    let sequence = 0
    const params = new URLSearchParams()
    for (const key of ['q', 'from', 'to']) if (applied[key]) params.set(key, applied[key])
    const path = `/api/admin/orders${params.size ? `?${params}` : ''}`
    const load = async () => {
      const request = ++sequence
      setLoading(true)
      try {
        const data = await api(path)
        if (current && request === sequence) { setOrders(data.orders); setError('') }
      } catch (err) { if (current && request === sequence) setError(err.message) }
      finally { if (current && request === sequence) setLoading(false) }
    }
    reload.current = load
    load()
    const timer = setInterval(load, 15000)
    return () => { current = false; clearInterval(timer); reload.current = null }
  }, [ready, applied])

  const apply = (values) => {
    if (values.from && values.to && values.from > values.to) {
      setFilterError('From date must be on or before To date.')
      return
    }
    setFilterError('')
    setApplied({ ...values, q: values.q.trim() })
  }
  const today = () => {
    const now = new Date()
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const values = { ...draft, from: date, to: date }
    setDraft(values)
    apply(values)
  }
  const clear = () => {
    const values = { q: '', from: '', to: '' }
    setDraft(values)
    setFilter('')
    apply(values)
  }

  if (redirect) return <Navigate to={redirect} replace />
  if (!ready) return null

  const count = (status) => orders.filter((order) => order.status === status).length
  const chip = (active) => `border text-sm px-4 py-1 ${active ? 'border-green-600 bg-green-600 text-white' : 'border-gray-300 text-gray-700'}`
  const shown = orders ? orders.filter((order) => !filter || order.status === filter) : []

  return (
    <ManagerLayout title="ORDERS">
      <form onSubmit={(event) => { event.preventDefault(); apply(draft) }} className="mb-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-gray-700">Search orders<input type="search" value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} placeholder="Order number, customer name or email" className="border border-gray-300 px-3 py-2" maxLength={255} /></label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-gray-700">From date<input type="date" value={draft.from} onChange={(event) => setDraft({ ...draft, from: event.target.value })} className="border border-gray-300 px-3 py-2" /></label>
          <label className="flex flex-col gap-1 text-sm text-gray-700">To date<input type="date" value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} className="border border-gray-300 px-3 py-2" /></label>
          <button type="submit" className="bg-green-600 px-4 py-2 text-sm text-white">Apply filters</button>
          <button type="button" onClick={today} className="border border-gray-300 px-4 py-2 text-sm">Today</button>
          <button type="button" onClick={clear} className="px-3 py-2 text-sm text-green-700 underline">Clear filters</button>
        </div>
      </form>
      {filterError && <p role="alert" className="mb-3 text-sm text-red-700">{filterError}</p>}
      {error && <p role="alert" className="mb-3 text-sm text-red-700">Could not refresh orders: {error}{orders && ' Showing the last successful results.'} <button type="button" onClick={() => reload.current?.()} className="underline">Retry orders</button></p>}
      {loading && <p role="status" className="mb-3 text-sm text-gray-500">{orders ? 'Refreshing orders...' : 'Loading orders...'}</p>}
      {orders && (
        <>
          <p className="mb-3 text-xs text-gray-500">Status counts reflect the applied search and date filters. Dates include the entire selected day.</p>
          <div className="flex flex-wrap gap-2 mb-6">
            <button onClick={() => setFilter('')} aria-pressed={filter === ''} className={chip(filter === '')}>All ({orders.length})</button>
            {Object.keys(statusLabels).map((status) => (
              <button key={status} onClick={() => setFilter(status)} aria-pressed={filter === status} className={chip(filter === status)}>
                {statusLabels[status]} ({count(status)})
              </button>
            ))}
          </div>
          {shown.length === 0 && <p className="text-gray-600">No orders here.</p>}
          {shown.map((order) => (
            <OrderRow key={order.order_id} order={order} currency={currency} onChanged={() => reload.current?.()} />
          ))}
        </>
      )}
    </ManagerLayout>
  )
}

// =====================================================================
// /manager/delivery: queue, trips, routes and exceptions
// =====================================================================

const isFree = (vehicle) => vehicle.status === 'available' && !vehicle.current_trip_id


const TripCard = ({ trip, queue, onChanged, onViewRoute }) => {

  const [message, setMessage] = useState('')
  const [addId, setAddId] = useState('')

  // One helper for every change a manager makes to a trip.
  const act = async (method, path, body) => {
    try {
      const data = await api(`/api/admin/delivery/trips/${trip.trip_id}${path}`, body === undefined ? { method } : { method, body })
      setMessage(data.route_error ? `The route could not be planned: ${data.route_error}` : '')
      onChanged()
      return true
    } catch (err) {
      setMessage(err.message)
      return false
    }
  }

  const addOrder = async () => {
    if (await act('POST', '/orders', { order_id: Number(addId) })) setAddId('')
  }

  const planned = trip.status === 'planned'
  const stops = [...trip.stops].sort((a, b) => (a.stop_sequence ?? 99) - (b.stop_sequence ?? 99))

  return (
    <div className="py-4 border-t border-b text-gray-700 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <p className="font-medium">Trip #{trip.trip_id} · {trip.vehicle.name}</p>
          <p className="text-sm text-gray-500">
            Created {formatTime(trip.created_at)}
            {trip.started_at && ` · left ${formatTime(trip.started_at)}`}
            {trip.completed_at && ` · finished ${formatTime(trip.completed_at)}`}
          </p>
        </div>
        <p className="text-sm">{tripLabels[trip.status]}</p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Meter label="Orders" used={trip.order_count} limit={trip.vehicle.max_orders} />
        <Meter label="Weight" used={Number(trip.total_weight_lb)} limit={trip.vehicle.max_weight_lb} unit=" lb" />
      </div>
      {trip.capacity_problem && <p className="text-sm text-red-600">{trip.capacity_problem}</p>}

      {trip.route_planned
        ? <p className="text-sm text-gray-600">Route planned with {providerName(trip.route?.provider)}, about {trip.route?.total_minutes} min in total.</p>
        : <p className="text-sm text-red-600">No route planned yet, so this trip cannot be dispatched.</p>}
      <a href="#delivery-overview" onClick={() => onViewRoute(trip.trip_id)} className="text-sm text-green-700 underline">View trip #{trip.trip_id} on the delivery map</a>

      <div className="flex flex-col gap-2">
        {stops.length === 0 && <p className="text-sm text-gray-500">This trip has no orders yet.</p>}
        {stops.map((stop) => (
          <div key={stop.order_id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-sm">
            <p><span className="font-medium">{stop.stop_sequence || '-'}. {stop.order_number}</span> · {stop.customer_name} · {stop.address}</p>
            <div className="flex items-center gap-4 text-gray-500">
              <div><p>{stop.weight_lb} lb</p>{!stop.delivered_at && <ArrivalEstimate value={stop.est_arrival} />}</div>
              {planned
                ? <button onClick={() => act('DELETE', `/orders/${stop.order_id}`)} aria-label={`Remove ${stop.order_number} from trip ${trip.trip_id}`} className="text-sm text-gray-600 underline">Remove</button>
                : <p>{stop.delivered_at ? `Delivered ${formatTime(stop.delivered_at)}` : statusLabels[stop.status]}</p>}
            </div>
          </div>
        ))}
      </div>

      {trip.status === 'out_for_delivery' && (
        <p className="text-sm text-gray-600">
          {trip.last_report
            ? <>Latest vehicle report: <b>{trip.last_report}</b>{trip.last_position && ` at ${formatTime(trip.last_position.at)}`}</>
            : 'Waiting for the first report from the vehicle.'}
        </p>
      )}

      {planned && (
        <div className="flex flex-wrap items-center gap-3">
          <select aria-label={`Add an order to trip ${trip.trip_id}`} className="border border-gray-300 px-3 py-2 text-sm" value={addId} onChange={(e) => setAddId(e.target.value)}>
            <option value="">Add an order...</option>
            {queue.map((order) => (
              <option key={order.order_id} value={order.order_id}>{order.order_number} ({order.total_weight_lb} lb)</option>
            ))}
          </select>
          <button onClick={addOrder} disabled={!addId} className="border border-gray-300 text-sm px-4 py-2 disabled:opacity-50">ADD</button>
          <button onClick={() => act('POST', '/route')} className="text-sm text-green-600 underline">Re-plan route</button>
          <button
            onClick={() => act('POST', '/dispatch')}
            disabled={trip.order_count === 0 || !trip.route_planned || !!trip.capacity_problem}
            className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400 disabled:opacity-50 sm:ml-auto"
          >
            DISPATCH
          </button>
        </div>
      )}
      {message && <p className="text-sm text-red-600">{message}</p>}
    </div>
  )
}

// Pick waiting orders and a vehicle; the limits are checked before anything is sent.
const TripBuilder = ({ queue, vehicles, onChanged }) => {

  const [selected, setSelected] = useState([])
  const [vehicleId, setVehicleId] = useState('')
  const [created, setCreated] = useState('')
  const [error, setError] = useState('')

  const free = vehicles.filter(isFree)
  const vehicle = free.find((v) => String(v.vehicle_id) === vehicleId) || free[0]
  const picked = queue.filter((order) => selected.includes(order.order_id))
  const weight = picked.reduce((sum, order) => sum + Number(order.total_weight_lb), 0)

  let problem = ''
  if (vehicle && picked.length > vehicle.max_orders) {
    problem = `Trip has ${picked.length} orders; the vehicle limit is ${vehicle.max_orders}`
  } else if (vehicle && weight > Number(vehicle.max_weight_lb)) {
    problem = `Trip weighs ${round(weight)} lb; the vehicle limit is ${Number(vehicle.max_weight_lb)} lb`
  }

  const toggle = (orderId) => setSelected(selected.includes(orderId) ? selected.filter((id) => id !== orderId) : [...selected, orderId])

  const createTrip = async (body) => {
    setError('')
    setCreated('')
    try {
      const data = await api('/api/admin/delivery/trips', { method: 'POST', body })
      setSelected([])
      setCreated(`Trip #${data.trip.trip_id} was created with ${data.trip.order_count} orders.${data.route_error ? ` The route could not be planned: ${data.route_error}` : ''}`)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="flex flex-col lg:flex-row justify-between gap-10">
      <div className="w-full">
        {queue.length === 0 && <p className="text-gray-600">No orders are waiting for delivery.</p>}
        {queue.map((order) => (
          <label key={order.order_id} className="py-4 border-t border-b text-gray-700 flex items-center gap-4 cursor-pointer">
            <input type="checkbox" className="accent-green-600" checked={selected.includes(order.order_id)} onChange={() => toggle(order.order_id)} aria-label={`Select ${order.order_number}`} />
            <div>
              <p className="font-medium">{order.order_number}</p>
              <p className="text-sm text-gray-500">{order.total_weight_lb} lb · waiting {waited(order.waited_minutes)}</p>
              {order.unscheduled_reason && <p className="text-sm text-red-600">{order.unscheduled_reason}</p>}
            </div>
          </label>
        ))}
      </div>

      <div className="w-full lg:max-w-[450px] flex flex-col gap-4 self-start border border-gray-300 rounded px-4 py-4">
        <p className="font-medium text-sm text-gray-700">NEW TRIP</p>
        <select aria-label="Vehicle" className="border border-gray-300 px-3 py-2 w-full text-sm" value={vehicle ? String(vehicle.vehicle_id) : ''} onChange={(e) => setVehicleId(e.target.value)}>
          {vehicles.map((v) => (
            <option key={v.vehicle_id} value={v.vehicle_id} disabled={!isFree(v)}>
              {v.name}{isFree(v) ? '' : v.current_trip_id ? ` (on trip #${v.current_trip_id})` : ` (${v.status})`}
            </option>
          ))}
        </select>
        {vehicle ? (
          <>
            <Meter label="Selected orders" used={picked.length} limit={vehicle.max_orders} />
            <Meter label="Selected weight" used={weight} limit={vehicle.max_weight_lb} unit=" lb" />
          </>
        ) : (
          <p className="text-sm text-red-600">No vehicle is free right now.</p>
        )}
        {problem && <p className="text-sm text-red-600" role="alert">{problem}</p>}
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <button
          onClick={() => createTrip({ vehicle_id: vehicle.vehicle_id, order_ids: picked.map((order) => order.order_id) })}
          disabled={!vehicle || picked.length === 0 || !!problem}
          className="w-full bg-green-600 text-white text-sm px-8 py-3 active:bg-green-400 disabled:opacity-50"
        >
          CREATE TRIP FROM SELECTED
        </button>
        <button
          onClick={() => createTrip({ vehicle_id: vehicle.vehicle_id })}
          disabled={!vehicle || queue.length === 0}
          className="self-start text-sm text-green-600 underline disabled:opacity-50"
        >
          Fill a trip automatically, oldest orders first
        </button>
        {created && (
          <div className="bg-green-50 border border-green-600 px-5 py-4">
            <p className="text-sm font-medium text-green-700">{created}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export const ManagerDelivery = () => {

  const { ready, redirect } = useManager()
  const [queue, setQueue] = useState([])
  const [exceptions, setExceptions] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [trips, setTrips] = useState(null)
  const [tripFilter, setTripFilter] = useState('')
  const [selectedTrip, setSelectedTrip] = useState('')
  const [updated, setUpdated] = useState(null)
  const [error, setError] = useState('')

  const load = () => Promise.all([
    api('/api/admin/delivery/queue'),
    api('/api/admin/delivery/exceptions'),
    api('/api/admin/delivery/vehicles'),
    api('/api/admin/delivery/trips'),
  ])
    .then(([waiting, problems, fleet, allTrips]) => {
      setQueue(waiting.orders)
      setExceptions(problems.orders)
      setVehicles(fleet.vehicles)
      setTrips(allTrips.trips)
      setError('')
      setUpdated(new Date())
    })
    .catch((err) => setError(err.message))

  useEffect(() => {
    if (!ready) return
    load()
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [ready])

  if (redirect) return <Navigate to={redirect} replace />
  if (!ready) return null

  const shownTrips = trips ? trips.filter((trip) => !tripFilter || trip.status === tripFilter) : []

  return (
    <ManagerLayout title="DELIVERY">
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <Section text1="DELIVERY" text2="MAP">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500"><p>{updated ? `Last refreshed ${updated.toLocaleTimeString()}. Updates every 10 seconds.` : 'Waiting for the first update.'}</p><button type="button" onClick={load} className="text-green-700 underline">Refresh deliveries</button></div>
        <DeliveryOverview trips={trips} selectedId={selectedTrip} onSelect={setSelectedTrip} showStops={false} />
      </Section>

      <Section text1={'NEEDS'} text2={'ATTENTION'}>
        {exceptions.length === 0 && <p className="text-sm text-gray-600">Every waiting order can be scheduled.</p>}
        {exceptions.length > 0 && (
          <div className="bg-red-50 border border-red-600 px-5 py-4 flex flex-col gap-1">
            <p className="font-medium text-red-700">These orders cannot be scheduled right now</p>
            {exceptions.map((order) => (
              <p key={order.order_id} className="text-sm text-gray-700">
                <span className="font-medium">{order.order_number}</span> · {order.total_weight_lb} lb · {order.reason}
              </p>
            ))}
          </div>
        )}
      </Section>

      <Section text1={'WAITING FOR'} text2={'DELIVERY'}>
        <TripBuilder queue={queue} vehicles={vehicles} onChanged={load} />
      </Section>

      <Section text1={'DELIVERY'} text2={'TRIPS'}>
        <select aria-label="Filter trips" className="self-start border border-gray-300 px-3 py-2 text-sm" value={tripFilter} onChange={(e) => setTripFilter(e.target.value)}>
          <option value="">All trips</option>
          {Object.keys(tripLabels).map((status) => (
            <option key={status} value={status}>{tripLabels[status]}</option>
          ))}
        </select>
        {trips && shownTrips.length === 0 && <p className="text-gray-600">No trips here yet.</p>}
        <div>
          {shownTrips.map((trip) => (
            <TripCard key={trip.trip_id} trip={trip} queue={queue} onChanged={load} onViewRoute={setSelectedTrip} />
          ))}
        </div>
      </Section>
    </ManagerLayout>
  )
}
