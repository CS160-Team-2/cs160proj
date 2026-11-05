import React, { useContext, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import DeliveryOverview from '../components/DeliveryOverview'

const EmployeeDelivery = () => {
  const { user } = useContext(StoreContext)
  const staff = user && ['employee', 'manager'].includes(user.role)
  const [trips, setTrips] = useState(null)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    if (!staff) return
    let current = true
    let loading = false
    const load = async () => {
      if (loading) return
      loading = true
      try {
        const data = await api('/api/staff/delivery/trips')
        if (current) { setTrips(data.trips); setError(''); setUpdated(new Date()) }
      } catch (err) { if (current) setError(err.message) }
      finally { loading = false }
    }
    load()
    const timer = setInterval(load, 10000)
    return () => { current = false; clearInterval(timer) }
  }, [staff, refresh])

  if (user === undefined) return <p role="status">Checking your account...</p>
  if (!user) return <Navigate to="/login?next=/delivery" replace />
  if (!staff) return <Navigate to="/orders" replace />
  return (
    <div className="border-t-2 pt-14 flex flex-col gap-6">
      <div className="text-2xl"><TextContent text1="DELIVERY" text2="TRACKING" /></div>
      <div className="flex flex-wrap gap-4 text-sm"><Link to="/inventory" className="text-green-700 underline">Inventory</Link>{user.role === 'manager' && <Link to="/manager/delivery" className="text-green-700 underline">Manage delivery trips</Link>}</div>
      <p className="text-sm text-gray-600">View delivery routes, stop progress, and vehicle reports. Trip creation and dispatch are managed by your manager.</p>
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-500"><p>{updated ? `Last refreshed ${updated.toLocaleTimeString()}. Updates every 10 seconds.` : 'Waiting for the first update.'}</p><button type="button" onClick={() => setRefresh((value) => value + 1)} className="text-green-700 underline">Refresh deliveries</button></div>
      {error && <p role="alert" className="text-sm text-red-700">Could not refresh deliveries: {error}{trips && ' Showing the last successful update.'}</p>}
      <DeliveryOverview trips={trips} />
    </div>
  )
}

export default EmployeeDelivery
