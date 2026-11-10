import React, { useState } from 'react'
import { api } from '../api'

export default function SimulationRecovery({ trip, onChanged }) {
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  if (trip.vehicle_mode !== 'simulated' || trip.status !== 'out_for_delivery') return null
  const stops = trip.stops.filter((stop) => !stop.delivered_at)
  const complete = async () => {
    if (busy) return
    setBusy(true); setError('')
    try {
      await api(`/api/admin/delivery/trips/${trip.trip_id}/simulation/stops/${selected.order_id}/complete`, { method: 'POST', body: { confirmed: true } })
      setNotice(`Demo delivery recorded for ${selected.order_number}.`)
      setSelected(null)
      await onChanged()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <section aria-label={`Demo recovery for trip ${trip.trip_id}`} className="border border-amber-400 bg-amber-50 p-4 text-sm">
    <h3 className="font-medium">Simulated delivery recovery</h3>
    <p className="mt-1">If Flask restarted or the simulator stopped, confirm each unfinished demo stop here. This records a simulated delivery, updates customer tracking, and frees the vehicle after the last stop. It does not restart the driving animation.</p>
    <div className="flex flex-wrap gap-3 mt-3">{stops.map((stop) => <button key={stop.order_id} disabled={busy} onClick={() => { setSelected(stop); setError(''); setNotice('') }} className="border border-amber-600 bg-white px-3 py-2 disabled:opacity-50">Demo: complete {stop.order_number}</button>)}</div>
    {selected && <div role="dialog" aria-label={`Confirm demo delivery ${selected.order_number}`} className="mt-4 border p-3 bg-white">
      <p>Record {selected.order_number} as delivered in this simulation? Your manager account and the time will be recorded in its history.</p>
      <div className="flex flex-wrap gap-3 mt-3"><button disabled={busy} onClick={complete} className="bg-amber-800 text-white px-3 py-2">{busy ? 'Recording...' : 'Confirm demo completion'}</button><button autoFocus disabled={busy} onClick={() => setSelected(null)} className="border px-3 py-2">Cancel demo completion</button></div>
    </div>}
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
    {notice && <p role="status" className="mt-3 text-green-800">{notice}</p>}
  </section>
}
