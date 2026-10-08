import React, { useContext, useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'

const statusLabels = {
  placed: 'Order placed',
  awaiting_delivery: 'Awaiting delivery',
  assigned_to_trip: 'Assigned to a trip',
  out_for_delivery: 'Out for delivery',
  delivered: 'Delivered',
}

const formatTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

// Customers only; anyone else is sent to sign in.
const useCustomer = () => {
  const { user } = useContext(StoreContext)
  const { pathname } = useLocation()
  if (user === undefined) return { ready: false }
  if (!user) return { ready: false, redirect: `/login?next=${pathname}` }
  return { ready: true }
}

// /orders: the customer's order history
export const OrderHistory = () => {

  const { currency } = useContext(StoreContext)
  const { ready, redirect } = useCustomer()
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ready) return
    api('/api/orders').then((data) => setOrders(data.orders)).catch((err) => setError(err.message))
  }, [ready])

  if (redirect) return <Navigate to={redirect} replace />

  return (
    <div className="border-t-2 pt-14">
      <div className="text-2xl mb-6">
        <TextContent text1={'MY'} text2={'ORDERS'} />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {orders && orders.length === 0 && <p className="text-gray-600">You have not placed any orders yet.</p>}
      {orders && orders.map((order) => (
        <Link key={order.order_number} to={`/orders/${order.order_number}`} className="py-4 border-t border-b text-gray-700 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-gray-50">
          <div>
            <p className="font-medium">{order.order_number}</p>
            <p className="text-sm text-gray-500">{formatTime(order.placed_at)} · {order.item_count} items</p>
          </div>
          <p className="text-sm">{statusLabels[order.status]}</p>
          <p className="font-medium">{currency}{order.grand_total}</p>
        </Link>
      ))}
    </div>
  )
}

// /orders/:orderNumber: one order, its items and live tracking
export const OrderDetail = () => {

  const { orderNumber } = useParams()
  const { state } = useLocation()
  const { currency } = useContext(StoreContext)
  const { ready, redirect } = useCustomer()
  const [order, setOrder] = useState(null)
  const [tracking, setTracking] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ready) return
    const load = () => Promise.all([
      api(`/api/orders/${orderNumber}`),
      api(`/api/orders/${orderNumber}/tracking`),
    ]).then(([detail, track]) => {
      setOrder(detail.order)
      setTracking(track)
    }).catch((err) => setError(err.message))

    load()
    // Delivery updates arrive on their own, so check again every 15 seconds.
    const timer = setInterval(load, 15000)
    return () => clearInterval(timer)
  }, [ready, orderNumber])

  if (redirect) return <Navigate to={redirect} replace />
  if (error) return <p className="pt-14 text-center text-red-600">{error}</p>
  if (!order || !tracking) return null

  return (
    <div className="border-t-2 pt-10 flex flex-col gap-10">
      {state?.justPlaced && (
        <div className="bg-green-50 border border-green-600 px-5 py-4">
          <p className="font-medium text-green-700">Thank you! Your order has been placed.</p>
          <p className="text-sm text-gray-600">Your order number is {order.order_number}.</p>
        </div>
      )}

      <div>
        <div className="text-2xl mb-2">
          <TextContent text1={'ORDER'} text2={order.order_number} />
        </div>
        <p className="text-sm text-gray-500">Placed {formatTime(order.placed_at)}</p>
      </div>

      {/* Tracking */}
      <ol className="flex flex-col sm:flex-row gap-4 sm:gap-2">
        {tracking.steps.map((step) => (
          <li key={step.status} className="flex-1 flex sm:flex-col gap-3 sm:gap-2">
            <span className={`h-2 sm:w-full w-2 sm:h-2 shrink-0 mt-1.5 sm:mt-0 ${step.done ? 'bg-green-600' : 'bg-gray-200'}`} />
            <div>
              <p className={`text-sm ${step.done ? 'font-medium text-gray-800' : 'text-gray-400'}`}>{statusLabels[step.status]}</p>
              {step.reached_at && <p className="text-xs text-gray-500">{formatTime(step.reached_at)}</p>}
            </div>
          </li>
        ))}
      </ol>
      {tracking.estimated_arrival && (
        <p className="text-gray-700">Estimated arrival: <b>{formatTime(tracking.estimated_arrival)}</b></p>
      )}

      {/* Items and totals */}
      <div className="flex flex-col sm:flex-row gap-10 justify-between">
        <div className="flex-1 flex flex-col gap-2 text-sm text-gray-700">
          {order.items.map((item) => (
            <div key={item.product_id} className="flex justify-between border-b py-2">
              <p>{item.quantity} x {item.name}</p>
              <p>{currency}{Number(item.line_total).toFixed(2)}</p>
            </div>
          ))}
          <p className="text-gray-500 mt-2">
            Delivering to {order.address.street}, {order.address.city}, {order.address.state} {order.address.zip_code}
          </p>
          {order.payment && <p className="text-gray-500">Paid with card ending {order.payment.card_last4}</p>}
        </div>

        <div className="w-full sm:w-[320px] flex flex-col gap-2 text-sm">
          <Row label="Subtotal" value={`${currency}${order.subtotal}`} />
          <Row label="Total weight" value={`${order.total_weight_lb} lb`} />
          <Row label="Delivery fee" value={order.delivery_fee === '0.00' ? 'Free' : `${currency}${order.delivery_fee}`} />
          <Row label="Tax" value={`${currency}${order.tax}`} />
          <hr />
          <div className="flex justify-between text-base"><b>Total</b><b>{currency}{order.grand_total}</b></div>
        </div>
      </div>

      <Link to="/orders" className="text-sm text-green-600 underline">See all my orders</Link>
    </div>
  )
}

const Row = ({ label, value }) => (
  <div className="flex justify-between">
    <p>{label}</p>
    <p>{value}</p>
  </div>
)
