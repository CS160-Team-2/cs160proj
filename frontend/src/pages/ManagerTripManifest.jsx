import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import ManagerAccess from '../components/ManagerAccess'
import ManagerLayout from '../components/ManagerLayout'

// Spreadsheet programs interpret leading = + - @ or control characters as
// formulas, even inside quoted CSV. Prefix those cells before quoting them.
export const csvCell = (value) => {
  let text = String(value ?? '')
  if (/^[\s]*[=+@-]|^[\t\r\n]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export const manifestCsv = (trip) => {
  const stops = [...trip.stops].sort((a, b) => (a.stop_sequence ?? 999) - (b.stop_sequence ?? 999))
  return '\uFEFF' + [
    ['Trip', 'Vehicle', 'Trip status', 'Stop', 'Order', 'Customer', 'Address', 'Weight (lb)', 'Estimated arrival', 'Delivered at'],
    ...stops.map((s, i) => [trip.trip_id, trip.vehicle.name, trip.status, s.stop_sequence ?? i + 1,
      s.order_number, s.customer_name, s.address, s.weight_lb, s.est_arrival, s.delivered_at]),
  ].map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n'
}

function Manifest() {
  const { tripId } = useParams()
  const [trip, setTrip] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [generatedAt, setGeneratedAt] = useState(null)
  useEffect(() => {
    let current = true
    setTrip(null); setError('')
    api(`/api/admin/delivery/trips/${encodeURIComponent(tripId)}`).then((reply) => {
      if (current) { setTrip(reply.trip); setGeneratedAt(new Date()) }
    }).catch((err) => { if (current) setError(err.message) })
    return () => { current = false }
  }, [tripId, retry])
  const download = () => {
    const url = URL.createObjectURL(new Blob([manifestCsv(trip)], { type: 'text/csv;charset=utf-8;' }))
    const a = document.createElement('a')
    a.href = url; a.download = `trip-${trip.trip_id}-stops.csv`; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <ManagerLayout title="TRIP STOP LIST">
    <div className="print:hidden flex flex-wrap gap-3 mb-5 text-sm">
      <Link className="text-green-700 underline" to={`/manager/delivery?trip=${encodeURIComponent(tripId)}#trip-${encodeURIComponent(tripId)}`}>Back to trip</Link>
      {trip && <><button onClick={() => window.print()} className="border px-4 py-2">Print stop list</button><button onClick={download} className="border px-4 py-2">Download stops CSV</button><button onClick={() => setRetry((n) => n + 1)} className="underline text-green-700">Refresh stop list</button></>}
    </div>
    {error && <p role="alert" className="text-red-700">{error} <button className="underline" onClick={() => setRetry((n) => n + 1)}>Retry stop list</button></p>}
    {!trip && !error && <p role="status">Loading trip stop list...</p>}
    {trip && <section className="min-w-0 text-gray-800" aria-label="Trip stop list">
      <h1 className="text-2xl font-semibold mb-2">Trip #{trip.trip_id} stop list</h1>
      <p className="break-words">{trip.vehicle.name} · {trip.status.replaceAll('_', ' ')} · {trip.order_count} orders · {trip.total_weight_lb} lb</p>
      <p className="text-sm text-gray-600">Generated {generatedAt?.toLocaleString()}. This is a snapshot; refresh before departure.</p>
      <p className="text-sm mt-2">{trip.route_planned ? 'Stops follow the saved planned route.' : 'No route is planned. Stop order is provisional; re-plan before dispatch.'}</p>
      {trip.stops.length === 0 && <p className="my-5">This trip has no stops.</p>}
      <ol className="divide-y border-y my-5">{[...trip.stops].sort((a, b) => (a.stop_sequence ?? 999) - (b.stop_sequence ?? 999)).map((stop, i) => <li key={stop.order_id} className="py-4 break-words [break-inside:avoid]">
        <h2 className="font-medium">Stop {stop.stop_sequence ?? i + 1} · <Link className="text-green-700 underline print:text-black print:no-underline" to={`/manager?q=${encodeURIComponent(stop.order_number)}&open=${stop.order_id}`}>{stop.order_number}</Link></h2>
        <p>{stop.customer_name}</p><p>{stop.address}</p><p>{stop.weight_lb} lb</p>
        <p className="text-sm">{stop.delivered_at ? `Delivered: ${new Date(stop.delivered_at).toLocaleString()}` : stop.est_arrival ? `Estimated arrival: ${new Date(stop.est_arrival).toLocaleString()}` : 'Estimated arrival not available'}</p>
      </li>)}</ol>
    </section>}
  </ManagerLayout>
}

export default function ManagerTripManifest() { return <ManagerAccess><Manifest /></ManagerAccess> }
