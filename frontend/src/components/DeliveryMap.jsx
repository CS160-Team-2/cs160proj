import React, { useId } from 'react'
import RouteMap, { mapPoint } from './RouteMap'

export const reportLabel = (report) => ({
  en_route: 'On the way', at_stop: 'At a delivery stop', returning: 'Returning to the store',
  completed: 'Trip completed', problem: 'Vehicle needs attention',
}[report] || 'Location received')

export const VehicleReport = ({ position, report, updatedAt, completed = false }) => {
  const stale = updatedAt && Date.now() - new Date(updatedAt).getTime() > 120000
  return (
    <div className="text-sm text-gray-600" aria-live="polite">
      <p>{completed ? 'Delivery completed.' : position ? <>Latest vehicle report: <b>{reportLabel(report)}</b>{updatedAt && ` · ${new Date(updatedAt).toLocaleString()}`}</> : 'Waiting for the vehicle to report its first position.'}</p>
      {position && stale && !completed && <p className="text-amber-800">The last report is over 2 minutes old. The marker shows the last known position.</p>}
      {report === 'problem' && !completed && <p className="text-red-700">A delivery issue was reported. Please wait for an update from the store.</p>}
    </div>
  )
}

const DeliveryMap = ({ trackingMap, status }) => {
  const id = useId()
  const store = mapPoint(trackingMap?.store)
  const destination = mapPoint(trackingMap?.destination)
  const vehicle = mapPoint(trackingMap?.vehicle_position)
  const completed = status === 'delivered' || trackingMap?.trip_status === 'completed'
  if (!store || !destination) return <p className="border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">Your delivery map will appear when the store assigns a route to your order.</p>

  const points = [
    { ...store, id: 'store', label: 'Store', color: '#2563eb' },
    { ...destination, id: 'destination', label: 'Your delivery address', color: completed ? '#6b7280' : '#16a34a' },
    ...(vehicle && !completed ? [{ ...vehicle, id: 'vehicle', kind: 'vehicle', label: 'Delivery vehicle', color: '#f59e0b' }] : []),
  ]
  return (
    <section className="border border-gray-200 bg-gray-50 p-4 flex flex-col gap-3" aria-labelledby={id}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h3 id={id} className="font-medium text-gray-800">Delivery map</h3><p className="text-xs text-gray-500">{completed ? 'Delivery completed' : vehicle ? 'Route from the latest vehicle position to your address' : 'Route from the store to your address'}</p></div>
        {trackingMap.directions_url && <a href={trackingMap.directions_url} target="_blank" rel="noreferrer" className="text-sm text-green-700 underline">Open route in Google Maps</a>}
      </div>
      <RouteMap points={points} scopeKey={`${store.latitude},${store.longitude}:${destination.latitude},${destination.longitude}`} directions={{ origin: !completed && vehicle ? vehicle : store, destination }} />
      <VehicleReport position={vehicle} report={trackingMap.last_report} updatedAt={trackingMap.last_updated} completed={completed} />
      {trackingMap.vehicle_mode === 'simulated' && <p className="text-xs text-amber-800">Simulated vehicle · reported positions are for the project demo.</p>}
      {!completed && <p className="text-xs text-gray-500">Tracking refreshes every 15 seconds. Vehicle movement appears when a new position is reported.</p>}
    </section>
  )
}

export default DeliveryMap
