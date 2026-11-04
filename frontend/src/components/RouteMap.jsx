import React, { useEffect, useId, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

export const mapPoint = (value) => {
  if (!value || value.latitude == null || value.longitude == null ||
      typeof value.latitude === 'boolean' || typeof value.longitude === 'boolean' ||
      String(value.latitude).trim() === '' || String(value.longitude).trim() === '') return null
  const latitude = Number(value.latitude)
  const longitude = Number(value.longitude)
  return Number.isFinite(latitude) && Number.isFinite(longitude) &&
    Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
    ? { ...value, latitude, longitude } : null
}

const lngLat = (point) => [point.longitude, point.latitude]
const lineData = (coordinates) => ({
  type: 'FeatureCollection',
  features: coordinates.length < 2 ? [] : [{
    type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates },
  }],
})

export const mapBounds = (coordinates) => {
  if (!coordinates.length) return null
  const longitudes = coordinates.map(([lng]) => lng)
  const latitudes = coordinates.map(([, lat]) => lat)
  return [[Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)]]
}

const Sketch = ({ points, label }) => {
  const id = useId()
  const [[west, south], [east, north]] = mapBounds(points.map(lngLat)) || [[0, 0], [1, 1]]
  const project = ({ longitude, latitude }) => ({
    x: 40 + (longitude - west) / Math.max(east - west, 0.002) * 560,
    y: 40 + (north - latitude) / Math.max(north - south, 0.002) * 240,
  })
  const stops = points.filter((point) => point.kind !== 'vehicle')
  return (
    <div>
      <svg viewBox="0 0 640 320" className="w-full border border-gray-200 bg-white" role="img" aria-label={label}>
        <defs><pattern id={id} width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e5e7eb" /></pattern></defs>
        <rect width="640" height="320" fill={`url(#${id})`} />
        <polyline points={stops.map((point) => { const { x, y } = project(point); return `${x},${y}` }).join(' ')} fill="none" stroke="#16a34a" strokeWidth="4" strokeDasharray="8 7" />
        {points.map((point) => {
          const { x, y } = project(point)
          return <g key={point.id}><title>{point.label}</title><circle cx={x} cy={y} r="12" fill={point.color} stroke="white" strokeWidth="3" /><text x={x + 16} y={y - 13} fontSize="12">{point.number || point.label}</text></g>
        })}
      </svg>
      <p className="mt-2 text-sm text-amber-800">Street map unavailable. This diagram shows approximate positions, not a road route.</p>
    </div>
  )
}

// Polling updates one map in place, preserving the user's zoom and pan.
const RouteMap = ({ points: rawPoints, path = [], directions, scopeKey, label = 'Interactive delivery street map', demo = false }) => {
  const token = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN?.trim()
  const points = rawPoints.map(mapPoint).filter(Boolean)
  // Server paths use [latitude, longitude]; GeoJSON uses [longitude, latitude].
  const savedPath = path.map(([latitude, longitude]) => mapPoint({ latitude, longitude })).filter(Boolean).map(lngLat)
  const [drivingPath, setDrivingPath] = useState([])
  const [routeError, setRouteError] = useState('')
  const [failed, setFailed] = useState(false)
  const [follow, setFollow] = useState(false)
  const container = useRef(null)
  const mapRef = useRef(null)
  const markers = useRef(new Map())
  const latest = useRef(null)
  const fitKey = useRef('')
  const lastLookup = useRef({ at: 0, destination: '' })
  const hasDirections = Boolean(directions?.origin && directions?.destination)
  const directionsKey = hasDirections ? JSON.stringify([directions.origin, directions.destination]) : ''
  const coordinates = hasDirections ? drivingPath : savedPath
  latest.current = { points, coordinates }
  const pointsKey = JSON.stringify(points)
  const hasPoints = points.length > 0
  const pathKey = JSON.stringify(coordinates)
  const framingKey = JSON.stringify([scopeKey, points.filter((point) => point.kind !== 'vehicle').map(lngLat)])

  const fit = () => {
    const data = latest.current
    const bounds = mapBounds([...data.points.map(lngLat), ...data.coordinates])
    if (bounds) mapRef.current?.fitBounds(bounds, { padding: 65, maxZoom: 16, duration: 500 })
  }

  useEffect(() => {
    if (!token || !hasDirections || failed) return
    const controller = new AbortController()
    const origin = mapPoint(directions.origin)
    const destination = mapPoint(directions.destination)
    if (!origin || !destination) return
    const destinationKey = JSON.stringify(lngLat(destination))
    const newDestination = lastLookup.current.destination !== destinationKey
    if (newDestination) setDrivingPath([])
    const delay = newDestination ? 0 : Math.max(0, 60000 - (Date.now() - lastLookup.current.at))
    let requestedAt = 0
    let settled = false
    const load = async () => {
      requestedAt = Date.now()
      lastLookup.current = { at: requestedAt, destination: destinationKey }
      const query = new URLSearchParams({ access_token: token, geometries: 'geojson', overview: 'full' })
      try {
        const response = await fetch(`https://api.mapbox.com/directions/v5/mapbox/driving/${lngLat(origin).join(',')};${lngLat(destination).join(',')}?${query}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Route lookup failed')
        const data = await response.json()
        const route = data.routes?.[0]?.geometry?.coordinates
        if (!Array.isArray(route) || route.length < 2) throw new Error('No driving route')
        if (!controller.signal.aborted) { setDrivingPath(route); setRouteError('') }
      } catch (error) {
        if (!controller.signal.aborted) {
          setDrivingPath([])
          setRouteError('The road route is temporarily unavailable. The address and vehicle markers are still shown.')
        }
      } finally { settled = true }
    }
    let timer
    if (delay) timer = setTimeout(load, delay)
    else load()
    return () => {
      controller.abort()
      clearTimeout(timer)
      // A cancelled request (including StrictMode's first mount) should
      // not delay the first successful route for a full minute.
      if (!settled && requestedAt && lastLookup.current.at === requestedAt) lastLookup.current.at = 0
    }
  }, [directionsKey, token, failed])

  useEffect(() => {
    if (!token || failed || !hasPoints) return
    let map
    let observer
    try {
      map = new mapboxgl.Map({
        container: container.current, accessToken: token,
        style: 'mapbox://styles/mapbox/streets-v12',
        center: latest.current.points[0] ? lngLat(latest.current.points[0]) : [-121.8811, 37.3352], zoom: 13,
      })
      mapRef.current = map
      map.addControl(new mapboxgl.NavigationControl(), 'top-right')
      map.on('load', () => {
        if (mapRef.current !== map) return
        map.addSource('delivery-route', { type: 'geojson', data: lineData(latest.current.coordinates) })
        map.addLayer({
          id: 'delivery-route-line', type: 'line', source: 'delivery-route',
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': '#16a34a', 'line-width': 5, 'line-opacity': 0.85, ...(demo ? { 'line-dasharray': [2, 2] } : {}) },
        })
        fit()
      })
      map.on('error', (event) => { if ([401, 403].includes(event.error?.status)) setFailed(true) })
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(() => map.resize())
        observer.observe(container.current)
      }
    } catch { setFailed(true) }
    return () => {
      observer?.disconnect()
      markers.current.forEach((marker) => marker.remove())
      markers.current.clear()
      map?.remove()
      mapRef.current = null
      fitKey.current = ''
    }
  }, [token, failed, demo, hasPoints])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const ids = new Set(points.map((point) => point.id))
    markers.current.forEach((marker, id) => {
      if (!ids.has(id)) { marker.remove(); markers.current.delete(id) }
    })
    points.forEach((point) => {
      let marker = markers.current.get(point.id)
      if (!marker || marker.ofsColor !== point.color || marker.ofsNumber !== point.number) {
        marker?.remove()
        const options = { color: point.color }
        if (point.number) {
          const element = document.createElement('div')
          element.textContent = String(point.number)
          element.style.cssText = `background:${point.color};color:white;border:3px solid white;border-radius:50%;width:30px;height:30px;display:grid;place-items:center;font:bold 13px sans-serif;box-shadow:0 1px 4px #555`
          element.setAttribute('aria-label', point.label)
          options.element = element
        }
        marker = new mapboxgl.Marker(options).setLngLat(lngLat(point)).addTo(map)
        marker.ofsColor = point.color
        marker.ofsNumber = point.number
        markers.current.set(point.id, marker)
      }
      marker.setLngLat(lngLat(point)).setPopup(new mapboxgl.Popup({ offset: 25 }).setText(point.label))
    })
    if (framingKey !== fitKey.current) { fit(); fitKey.current = framingKey }
    else if (follow) {
      const vehicle = points.find((point) => point.kind === 'vehicle')
      if (vehicle) map.easeTo({ center: lngLat(vehicle), duration: 600 })
    }
  }, [pointsKey, framingKey, follow, token, failed, demo])

  useEffect(() => {
    mapRef.current?.getSource('delivery-route')?.setData(lineData(coordinates))
  }, [pathKey])

  if (!points.length) return <p className="text-sm text-gray-600">A map will be available once the delivery address is confirmed.</p>
  return (
    <div className="flex flex-col gap-3">
      {token && !failed ? <>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <button type="button" onClick={fit} className="border border-gray-300 bg-white px-3 py-2">Fit route</button>
          {points.some((point) => point.kind === 'vehicle') && <label className="flex items-center gap-2"><input type="checkbox" checked={follow} onChange={(event) => setFollow(event.target.checked)} />Follow vehicle</label>}
        </div>
        <div ref={container} className="w-full h-[420px] border border-gray-200" role="img" aria-label={label} />
        {routeError && <p role="status" className="text-sm text-amber-800">{routeError}</p>}
      </> : <Sketch points={points} label="Delivery route diagram" />}
      {failed && <button type="button" className="self-start text-sm text-green-700 underline" onClick={() => { lastLookup.current = { at: 0, destination: '' }; setFailed(false) }}>Retry street map</button>}
      {demo && <p className="text-sm text-amber-800">Demo route: dashed lines show the offline plan, not directions along roads.</p>}
      <p className="text-xs text-gray-600">Blue: store · Green: delivery stops · Gray: delivered stops · Orange: latest vehicle position</p>
    </div>
  )
}

export default RouteMap
