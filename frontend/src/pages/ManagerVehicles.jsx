import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import ManagerAccess from '../components/ManagerAccess'
import ManagerLayout from '../components/ManagerLayout'
import useManagerList from '../useManagerList'

function VehicleForm({ vehicle, busy, error, onSave, onCancel }) {
  const [values, setValues] = useState(vehicle ? {
    name: vehicle.name, max_orders: String(vehicle.max_orders),
    max_weight_lb: vehicle.max_weight_lb, status: vehicle.status,
  } : { name: '', max_orders: '10', max_weight_lb: '200.00', status: 'available' })
  const change = (key) => (event) => setValues({ ...values, [key]: event.target.value })
  return <section className="border bg-gray-50 p-5 mb-6" aria-labelledby="vehicle-form-title">
    <h2 id="vehicle-form-title" className="font-medium mb-4">{vehicle ? 'Edit vehicle' : 'Add simulated vehicle'}</h2>
    <form onSubmit={(event) => { event.preventDefault(); onSave({ ...values, name: values.name.trim(), max_orders: Number(values.max_orders) }) }}>
      <fieldset disabled={busy} className="grid sm:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-sm">Vehicle name<input autoFocus value={values.name} onChange={change('name')} required maxLength={60} className="border bg-white px-3 py-2" /></label>
        <label className="flex flex-col gap-1 text-sm">Maximum orders<input type="number" min="1" max="10" step="1" value={values.max_orders} onChange={change('max_orders')} required className="border bg-white px-3 py-2" /></label>
        <label className="flex flex-col gap-1 text-sm">Maximum weight (lb)<input type="number" min="0.01" max="200" step="0.01" value={values.max_weight_lb} onChange={change('max_weight_lb')} required className="border bg-white px-3 py-2" /></label>
        <label className="flex flex-col gap-1 text-sm">Availability<select value={values.status} onChange={change('status')} className="border bg-white px-3 py-2"><option value="available">Available</option><option value="maintenance">Maintenance</option></select></label>
        <p className="text-xs text-gray-600 sm:col-span-2">Each trip must satisfy both limits: at most 10 orders and 200 lb. Dispatch controls the On trip status.</p>
        <div className="flex flex-wrap gap-3 sm:col-span-2"><button type="submit" className="bg-green-600 text-white px-4 py-2 text-sm">{busy ? 'Saving vehicle...' : vehicle ? 'Save vehicle changes' : 'Create vehicle'}</button><button type="button" onClick={onCancel} className="border bg-white px-4 py-2 text-sm">Cancel</button></div>
      </fieldset>
      {error && <p role="alert" className="text-red-700 mt-3">{error}</p>}
    </form>
  </section>
}

function Vehicles() {
  const { data, error, loading, refresh } = useManagerList('/api/admin/delivery/vehicles')
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')
  const open = (vehicle = null) => { setForm({ vehicle }); setFormError(''); setNotice('') }
  const save = async (values) => {
    if (busy) return
    const vehicle = form.vehicle
    setBusy(true); setFormError('')
    try {
      const reply = await api(vehicle ? `/api/admin/delivery/vehicles/${vehicle.vehicle_id}` : '/api/admin/delivery/vehicles', { method: vehicle ? 'PATCH' : 'POST', body: values })
      setForm(null); setNotice(`${vehicle ? 'Updated' : 'Created'} ${reply.vehicle.name}.`)
      await refresh()
    } catch (err) { setFormError(err.message) }
    finally { setBusy(false) }
  }
  return <ManagerLayout title="VEHICLES">
    <p className="text-sm text-gray-600 mb-4">Manage the simulated delivery fleet. Vehicles with a planned or dispatched trip cannot be edited until the trip finishes. Maintenance vehicles are excluded from new trips.</p>
    <div className="flex flex-wrap gap-4 mb-5"><button disabled={busy} onClick={() => open()} className="bg-green-600 text-white px-4 py-2 text-sm disabled:opacity-50">Add simulated vehicle</button><button disabled={busy} onClick={refresh} className="text-green-700 underline text-sm">Refresh vehicles</button></div>
    {notice && <p role="status" className="bg-green-50 text-green-800 p-3 mb-4">{notice}</p>}
    {error && <p role="alert" className="text-red-700 mb-4">Could not refresh vehicles: {error}{data && ' Showing the last successful results.'} <button onClick={refresh} className="underline">Retry vehicles</button></p>}
    {form && <VehicleForm key={form.vehicle?.vehicle_id || 'new'} vehicle={form.vehicle} busy={busy} error={formError} onSave={save} onCancel={() => setForm(null)} />}
    {loading && <p role="status">{data ? 'Refreshing vehicles...' : 'Loading vehicles...'}</p>}
    {data?.vehicles.length === 0 && <p>No vehicles have been added.</p>}
    <div className="grid md:grid-cols-2 gap-4 mt-4">{data?.vehicles.map((vehicle) => <article key={vehicle.vehicle_id} className="border p-4 text-sm min-w-0">
      <h2 className="font-medium break-words">{vehicle.name}</h2>
      <p>Maximum orders: {vehicle.max_orders} · Maximum weight: {vehicle.max_weight_lb} lb</p>
      <p>Status: {({ available: 'Available', maintenance: 'Maintenance', on_trip: 'On trip' })[vehicle.status] || vehicle.status}</p>
      {vehicle.current_trip_id ? <p>Current trip: #{vehicle.current_trip_id} · <Link to="/manager/delivery" className="text-green-700 underline">Open delivery board</Link></p> : <p>No active trip</p>}
      <button disabled={busy || loading || Boolean(vehicle.current_trip_id) || vehicle.status === 'on_trip'} onClick={() => open(vehicle)} aria-label={`Edit ${vehicle.name}`} className="text-green-700 underline mt-3 disabled:opacity-50">Edit vehicle</button>
      {(vehicle.current_trip_id || vehicle.status === 'on_trip') && <p className="text-xs text-gray-500 mt-1">Finish the active trip before editing.</p>}
    </article>)}</div>
  </ManagerLayout>
}

export default function ManagerVehicles() { return <ManagerAccess><Vehicles /></ManagerAccess> }
