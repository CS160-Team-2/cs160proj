import React, { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

const WIDTH = 640
const HEIGHT = 280
const PADDING = 42

const point = (value) => {
  if (!value) return null
  const latitude = Number(value.latitude)
  const longitude = Number(value.longitude)
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    ? { latitude, longitude }
    : null
}

const coordinates = (value) => [value.longitude, value.latitude]

const providerName = (provider) => ({
  google: 'Google Routes',
  mapbox: 'Mapbox',
  fake: 'offline demo provider',
}[provider] || 'mapping provider')

const projection = (points) => {
  const latitudes = points.map((item) => item.latitude)
  const longitudes = points.map((item) => item.longitude)
  const minLatitude = Math.min(...latitudes)
  const maxLatitude = Math.max(...latitudes)
  const minLongitude = Math.min(...longitudes)
  const maxLongitude = Math.max(...longitudes)
  const latitudeRange = Math.max(maxLatitude - minLatitude, 0.005)
  const longitudeRange = Math.max(maxLongitude - minLongitude, 0.005)

  return (item) => ({
    x: PADDING + ((item.longitude - minLongitude) / longitudeRange) * (WIDTH - PADDING * 2),
    y: PADDING + ((maxLatitude - item.latitude) / latitudeRange) * (HEIGHT - PADDING * 2),
  })
}

const SvgMarker = ({ at, color, label }) => (
  <g>
    <circle cx={at.x} cy={at.y} r="9" fill={color} stroke="white" strokeWidth="3" />
    <text x={at.x + 13} y={at.y - 11} fontSize="13" fill="#1f2937">{label}</text>
  </g>
)

const SchematicMap = ({ store, destination, vehicle }) => {
  const locations = [store, destination, ...(vehicle ? [vehicle] : [])]
  const project = projection(locations)
  const storeAt = project(store)
  const destinationAt = project(destination)
  const vehicleAt = vehicle ? project(vehicle) : null
  const route = [storeAt, ...(vehicleAt ? [vehicleAt] : []), destinationAt]
    .map(({ x, y }) => `${x},${y}`)
    .join(' ')

  return (
    <>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full min-h-48 bg-white border border-gray-200"
        role="img"
        aria-label="Delivery route from the store to the delivery address"
      >
        <defs>
          <pattern id="delivery-map-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e5e7eb" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#delivery-map-grid)" />
        <polyline
          points={route}
          fill="none"
          stroke="#16a34a"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={vehicleAt ? undefined : '10 8'}
        />
        <SvgMarker at={storeAt} color="#2563eb" label="Store" />
        {vehicleAt && <SvgMarker at={vehicleAt} color="#f59e0b" label="Vehicle" />}
        <SvgMarker at={destinationAt} color="#16a34a" label="Your address" />
      </svg>
      <p className="text-xs text-amber-700">
        Add VITE_MAPBOX_ACCESS_TOKEN to frontend/.env to enable the interactive street map.
      </p>
    </>
  )
}

const popup = (label) => new mapboxgl.Popup({ offset: 25 }).setText(label)

const marker = (map, value, color, label) => new mapboxgl.Marker({ color })
  .setLngLat(coordinates(value))
  .setPopup(popup(label))
  .addTo(map)

const routeUrl = (store, destination, token) => {
  const points = `${store.longitude},${store.latitude};${destination.longitude},${destination.latitude}`
  const query = new URLSearchParams({
    access_token: token,
    geometries: 'geojson',
    overview: 'full',
  })
  return `https://api.mapbox.com/directions/v5/mapbox/driving/${points}?${query}`
}

const routeFeature = (routeCoordinates) => ({
  type: 'Feature',
  properties: {},
  geometry: { type: 'LineString', coordinates: routeCoordinates },
})

const InteractiveMap = ({ store, destination, vehicle, token }) => {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const vehicleMarkerRef = useRef(null)

  const storeKey = `${store.latitude},${store.longitude}`
  const destinationKey = `${destination.latitude},${destination.longitude}`

  useEffect(() => {
    const controller = new AbortController()
    mapboxgl.accessToken = token

    const center = [
      (store.longitude + destination.longitude) / 2,
      (store.latitude + destination.latitude) / 2,
    ]
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/streets-v12',
      center,
      zoom: 13,
    })
    mapRef.current = map
    map.addControl(new mapboxgl.NavigationControl(), 'top-right')

    const storeMarker = marker(map, store, '#2563eb', 'Store')
    const destinationMarker = marker(map, destination, '#16a34a', 'Your address')

    map.fitBounds([coordinates(store), coordinates(destination)], {
      padding: 70,
      maxZoom: 15,
    })

    map.on('load', async () => {
      let routeCoordinates = [coordinates(store), coordinates(destination)]
      try {
        const response = await fetch(routeUrl(store, destination, token), {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`Mapbox Directions returned ${response.status}`)
        const data = await response.json()
        if (data.routes?.[0]?.geometry?.coordinates?.length) {
          routeCoordinates = data.routes[0].geometry.coordinates
        }
      } catch (error) {
        if (error.name === 'AbortError') return
        // The street map and markers remain usable if route lookup is temporarily unavailable.
      }

      if (!mapRef.current) return
      map.addSource('delivery-route', {
        type: 'geojson',
        data: routeFeature(routeCoordinates),
      })
      map.addLayer({
        id: 'delivery-route-line',
        type: 'line',
        source: 'delivery-route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#16a34a', 'line-width': 5, 'line-opacity': 0.9 },
      })
    })

    return () => {
      controller.abort()
      vehicleMarkerRef.current?.remove()
      vehicleMarkerRef.current = null
      storeMarker.remove()
      destinationMarker.remove()
      map.remove()
      mapRef.current = null
    }
  }, [storeKey, destinationKey, token])

  const vehicleKey = vehicle ? `${vehicle.latitude},${vehicle.longitude}` : ''
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (!vehicle) {
      vehicleMarkerRef.current?.remove()
      vehicleMarkerRef.current = null
      return
    }

    if (vehicleMarkerRef.current) {
      vehicleMarkerRef.current.setLngLat(coordinates(vehicle))
    } else {
      vehicleMarkerRef.current = marker(map, vehicle, '#f59e0b', 'Delivery vehicle')
    }

    map.fitBounds([coordinates(store), coordinates(destination), coordinates(vehicle)], {
      padding: 70,
      maxZoom: 15,
    })
  }, [vehicleKey, storeKey, destinationKey])

  return (
    <div
      ref={containerRef}
      className="w-full h-[420px] border border-gray-200"
      role="img"
      aria-label="Interactive delivery street map from the store to the delivery address"
    />
  )
}

const DeliveryMap = ({ trackingMap }) => {
  if (!trackingMap) return null

  const store = point(trackingMap.store)
  const destination = point(trackingMap.destination)
  const vehicle = point(trackingMap.vehicle_position)
  if (!store || !destination) return null

  const token = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN?.trim()

  return (
    <section className="border border-gray-200 bg-gray-50 p-4 flex flex-col gap-3" aria-labelledby="delivery-map-title">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
        <div>
          <h3 id="delivery-map-title" className="font-medium text-gray-800">Delivery map</h3>
          <p className="text-xs text-gray-500">Route planned with {providerName(trackingMap.provider)}.</p>
        </div>
        <a
          href={trackingMap.directions_url}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-green-700 underline"
        >
          Open route in Google Maps
        </a>
      </div>

      {token
        ? <InteractiveMap store={store} destination={destination} vehicle={vehicle} token={token} />
        : <SchematicMap store={store} destination={destination} vehicle={vehicle} />}

      {vehicle ? (
        <p className="text-sm text-gray-600">
          Latest vehicle report: <b>{trackingMap.last_report || 'location received'}</b>
          {trackingMap.last_updated && ` at ${new Date(trackingMap.last_updated).toLocaleString()}`}
        </p>
      ) : (
        <p className="text-sm text-gray-600">The live vehicle marker will appear after the vehicle reports its first location.</p>
      )}
    </section>
  )
}

export default DeliveryMap
