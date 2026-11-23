import React, { useContext, useEffect, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import DeliveryOverview from '../components/DeliveryOverview'
import { loginUrl } from '../redirects'

// A titled block on the page, in the same style as the other pages' headings.
const Block = ({ text1, text2, children }) => (
  <section className="flex flex-col gap-3">
    <div className="text-xl"><TextContent text1={text1} text2={text2} /></div>
    {children}
  </section>
)

const vehicleLabels = { available: 'Available', on_trip: 'On a trip', maintenance: 'In maintenance' }

// Read-only delivery status for staff: orders waiting, orders that cannot be scheduled, vehicles, and trips with their routes.
const EmployeeDelivery = () => {
  const { user } = useContext(StoreContext)
  const location = useLocation()
  const isEmployee = user?.role === 'employee'
  const [trips, setTrips] = useState(null)
  const [board, setBoard] = useState(null)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    if (!isEmployee) return
    let current = true
    let loading = false
    const load = async () => {
      if (loading) return
      loading = true
      try {
        const [tripData, boardData] = await Promise.all([api('/api/staff/delivery/trips'), api('/api/staff/delivery/board')])
        if (current) { setTrips(tripData.trips); setBoard(boardData); setError(''); setUpdated(new Date()) }
      } catch (err) { if (current) setError(err.message) }
      finally { loading = false }
    }
    load()
    const timer = setInterval(load, 10000)
    return () => { current = false; clearInterval(timer) }
  }, [isEmployee, refresh])

  if (user === undefined) return <p role="status">Checking your account...</p>
  if (!user) return <Navigate to={loginUrl('/delivery')} replace />
  if (user.role === 'manager') return <Navigate to={{ pathname: '/manager/delivery', search: location.search, hash: location.hash }} replace />
  if (!isEmployee) return <Navigate to="/orders" replace />
  return (
    <div className="border-t-2 pt-14 flex flex-col gap-6">
      <div className="text-2xl"><TextContent text1="DELIVERY" text2="TRACKING" /></div>
      <div className="flex flex-wrap gap-4 text-sm"><Link to="/inventory" className="text-green-700 underline">Inventory</Link></div>
      <p className="text-sm text-gray-600">View delivery routes, stop progress, and vehicle reports. Trip creation and dispatch are managed by your manager.</p>
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-500"><p>{updated ? `Last refreshed ${updated.toLocaleTimeString()}. Updates every 10 seconds.` : 'Waiting for the first update.'}</p><button type="button" onClick={() => setRefresh((value) => value + 1)} className="text-green-700 underline">Refresh deliveries</button></div>
      {error && <p role="alert" className="text-sm text-red-700">Could not refresh deliveries: {error}{trips && ' Showing the last successful update.'}</p>}

      <Block text1="WAITING FOR" text2="DELIVERY">
        {board === null && <p role="status" className="text-gray-600">Loading waiting orders...</p>}
        {board && board.waiting.length === 0 && <p className="text-sm text-gray-600">No orders are waiting. Every ready order is on a trip.</p>}
        {board && board.waiting.length > 0 && (
          <ul className="divide-y divide-gray-200 border border-gray-200" aria-label="Orders waiting for delivery">
            {board.waiting.map((order) => (
              <li key={order.order_number} className="p-3 flex flex-wrap justify-between gap-2 text-sm">
                <span><b>{order.order_number}</b> · {order.total_weight_lb} lb</span>
                <span className="text-gray-600">Waiting {order.waited_minutes} min for a trip</span>
              </li>
            ))}
          </ul>
        )}
      </Block>

      {board && board.problems.length > 0 && (
        <Block text1="NEEDS" text2="ATTENTION">
          <div className="bg-red-50 border border-red-600 px-5 py-4 flex flex-col gap-1">
            <p className="font-medium text-red-700">These orders cannot be scheduled right now</p>
            {board.problems.map((order) => (
              <p key={order.order_number} className="text-sm text-gray-700"><span className="font-medium">{order.order_number}</span> · {order.total_weight_lb} lb · {order.reason}</p>
            ))}
          </div>
        </Block>
      )}

      <Block text1="DELIVERY" text2="VEHICLES">
        {board && board.vehicles.length === 0 && <p className="text-sm text-gray-600">No vehicles have been added yet.</p>}
        {board && board.vehicles.length > 0 && (
          <ul className="grid gap-3 sm:grid-cols-2" aria-label="Delivery vehicles">
            {board.vehicles.map((vehicle) => (
              <li key={vehicle.vehicle_id} className="border border-gray-200 p-4 text-sm">
                <p className="font-medium">{vehicle.name}</p>
                <p className="text-gray-600">Up to {vehicle.max_orders} orders and {vehicle.max_weight_lb} lb</p>
                <p className="mt-1">{vehicle.current_trip_id ? `On trip #${vehicle.current_trip_id}` : (vehicleLabels[vehicle.status] || vehicle.status)}</p>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block text1="DELIVERY" text2="TRIPS">
        <DeliveryOverview trips={trips} />
      </Block>
    </div>
  )
}

export default EmployeeDelivery
