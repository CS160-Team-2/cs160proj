import React, { useState } from 'react'
import TripMap from './TripMap'
import ArrivalEstimate from './ArrivalEstimate'

const labels = { planned: 'Planned', out_for_delivery: 'Out for delivery', completed: 'Completed' }

const DeliveryOverview = ({ trips, selectedId, onSelect, showStops = true }) => {
  const [localId, setLocalId] = useState('')
  if (trips === null) return <p role="status" className="text-gray-600">Loading delivery trips...</p>
  const active = trips.filter((trip) => trip.status === 'out_for_delivery')
  const planned = trips.filter((trip) => trip.status === 'planned')
  const selected = trips.find((trip) => String(trip.trip_id) === String(selectedId ?? localId)) || active[0] || planned[0] || trips[0]
  const choose = (value) => { setLocalId(value); onSelect?.(value) }
  const remaining = selected?.stops.filter((stop) => !stop.delivered_at).length || 0

  return (
    <div id="delivery-overview" className="flex flex-col gap-4 scroll-mt-24">
      <div className="grid grid-cols-3 gap-3 text-center">
        {[['Out for delivery', active.length], ['Planned trips', planned.length], ['Completed trips', trips.length - active.length - planned.length]].map(([label, value]) => <div key={label} className="border border-gray-200 p-3"><p className="text-2xl font-semibold text-green-700">{value}</p><p className="text-xs sm:text-sm text-gray-600">{label}</p></div>)}
      </div>
      {selected ? <>
        <label className="flex flex-col sm:flex-row sm:items-center gap-2 text-sm">Delivery trip
          <select className="border border-gray-300 bg-white p-2" value={selected.trip_id} onChange={(event) => choose(event.target.value)}>
            {[...active, ...planned, ...trips.filter((trip) => trip.status === 'completed')].map((trip) => <option key={trip.trip_id} value={trip.trip_id}>Trip #{trip.trip_id} · {trip.vehicle.name} · {labels[trip.status]}</option>)}
          </select>
        </label>
        <p className="text-sm text-gray-700">{labels[selected.status]} · {selected.stops.length - remaining} of {selected.stops.length} stops delivered · {selected.total_weight_lb} lb</p>
        <TripMap trip={selected} />
        {showStops && <ol className="divide-y divide-gray-200 border border-gray-200">
          {[...selected.stops].sort((a, b) => (a.stop_sequence ?? 999) - (b.stop_sequence ?? 999)).map((stop, index) => <li key={stop.order_id} className="p-3 flex flex-wrap justify-between gap-2 text-sm"><span>Stop {stop.stop_sequence || index + 1} · <b>{stop.order_number}</b></span><div>{stop.delivered_at ? <span className="text-green-700">Delivered</span> : <><span>{selected.status === 'planned' ? 'Awaiting dispatch' : 'Pending delivery'}</span><ArrivalEstimate value={stop.est_arrival} /></>}</div></li>)}
        </ol>}
      </> : <p className="border border-gray-200 bg-gray-50 p-5 text-gray-600">There are no delivery trips yet. Maps appear after a manager creates a trip.</p>}
    </div>
  )
}

export default DeliveryOverview
