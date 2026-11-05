import React, { useId } from 'react'
import RouteMap from './RouteMap'
import { VehicleReport } from './DeliveryMap'

const TripMap = ({ trip }) => {
  const id = useId()
  const stops = [...trip.stops].sort((a, b) => (a.stop_sequence ?? 999) - (b.stop_sequence ?? 999))
  const points = [
    ...(trip.route?.store ? [{ ...trip.route.store, id: 'store', label: 'Store', color: '#2563eb' }] : []),
    ...stops.map((stop, index) => ({
      ...stop, id: `stop-${stop.order_id}`, number: stop.stop_sequence || index + 1,
      label: `Stop ${stop.stop_sequence || index + 1}: ${stop.order_number}${stop.delivered_at ? ' (delivered)' : ''}`,
      color: stop.delivered_at ? '#6b7280' : '#16a34a',
    })),
    ...(trip.last_position ? [{ ...trip.last_position, id: 'vehicle', kind: 'vehicle', label: trip.vehicle.name, color: '#f59e0b' }] : []),
  ]
  return (
    <section aria-labelledby={id} className="border border-gray-200 bg-gray-50 p-4 flex flex-col gap-3">
      <h3 id={id} className="font-medium">Trip #{trip.trip_id} route · {trip.vehicle.name}</h3>
      {trip.vehicle_mode === 'simulated' && <p className="text-xs text-amber-800">Simulated vehicle · reported positions are for the project demo.</p>}
      <RouteMap points={points} path={trip.route?.path || []} scopeKey={`trip-${trip.trip_id}`} demo={trip.route?.provider === 'fake'} label={`Interactive street map for trip ${trip.trip_id}`} />
      {!trip.route_planned && <p className="text-sm text-amber-800">A route has not been planned yet. Only confirmed stop positions are shown.</p>}
      <VehicleReport position={trip.last_position} report={trip.last_report} updatedAt={trip.last_position?.at} completed={trip.status === 'completed'} />
    </section>
  )
}

export default TripMap
