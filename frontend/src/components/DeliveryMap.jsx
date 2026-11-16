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
  const completed = status === 'delivered' || trackingMap?.trip_status === 'completed'
  const preview = trackingMap?.preview === true && !completed
  const vehicle = preview ? null : mapPoint(trackingMap?.vehicle_position)
  if (!store || !destination) return <p className="border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">Your delivery map is not available yet. Your order status is shown above.</p>

  const points = [
    { ...store, id: 'store', label: 'Store', color: '#2563eb' },
    { ...destination, id: 'destination', label: 'Your delivery address', color: completed ? '#6b7280' : '#16a34a' },
    ...(vehicle && !completed ? [{ ...vehicle, id: 'vehicle', kind: 'vehicle', label: 'Delivery vehicle', color: '#f59e0b' }] : []),
  ]
  return (
    <section className="border border-gray-200 bg-gray-50 p-4 flex flex-col gap-3" aria-labelledby={id}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h3 id={id} className="font-medium text-gray-800">{preview ? 'Delivery map preview' : 'Delivery map'}</h3><p className="text-xs text-gray-500">{preview ? 'Store and your delivery address. Your route will appear once your order is assigned to a planned delivery trip.' : completed ? 'Delivery completed' : vehicle ? 'Route from the latest vehicle position to your address' : 'Route from the store to your address'}</p></div>
        {!preview && trackingMap.directions_url && <a href={trackingMap.directions_url} target="_blank" rel="noreferrer" className="text-sm text-green-700 underline">Open route in Google Maps</a>}
      </div>
      <RouteMap points={points} scopeKey={`${store.latitude},${store.longitude}:${destination.latitude},${destination.longitude}`} preview={preview} directions={preview ? undefined : { origin: !completed && vehicle ? vehicle : store, destination }} />
      {preview && store.latitude === destination.latitude && store.longitude === destination.longitude && <p className="text-xs text-gray-600">The store and delivery markers overlap at this map location.</p>}
      {!preview && <VehicleReport position={vehicle} report={trackingMap.last_report} updatedAt={trackingMap.last_updated} completed={completed} />}
      {!preview && trackingMap.vehicle_mode === 'simulated' && <p className="text-xs text-amber-800">Simulated vehicle · reported positions are for the project demo.</p>}
      {!preview && !completed && <p className="text-xs text-gray-500">Tracking refreshes every 15 seconds. Vehicle movement appears when a new position is reported.</p>}
    </section>
  )
}

export default DeliveryMap
