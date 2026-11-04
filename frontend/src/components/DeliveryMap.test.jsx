import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import DeliveryMap from './DeliveryMap'
import TripMap from './TripMap'
import { mapBounds, mapPoint } from './RouteMap'

const mapbox = vi.hoisted(() => {
  const state = { maps: [], markers: [] }
  const Map = vi.fn(() => {
    const events = {}
    const source = { setData: vi.fn() }
    const instance = {
      events, source, addControl: vi.fn(), addSource: vi.fn(), addLayer: vi.fn(),
      getSource: vi.fn(() => source), fitBounds: vi.fn(), easeTo: vi.fn(), resize: vi.fn(), remove: vi.fn(),
      on: vi.fn((event, callback) => {
        events[event] = callback
        if (event === 'load') Promise.resolve().then(callback)
        return instance
      }),
    }
    state.maps.push(instance)
    return instance
  })
  const Marker = vi.fn((options) => {
    const instance = { options, setLngLat: vi.fn(() => instance), setPopup: vi.fn(() => instance), addTo: vi.fn(() => instance), remove: vi.fn() }
    state.markers.push(instance)
    return instance
  })
  const Popup = vi.fn(() => { const instance = { setText: vi.fn(() => instance) }; return instance })
  return { state, Map, Marker, Popup, NavigationControl: vi.fn() }
})
vi.mock('mapbox-gl', () => ({ default: { Map: mapbox.Map, Marker: mapbox.Marker, Popup: mapbox.Popup, NavigationControl: mapbox.NavigationControl } }))

const planned = {
  provider: 'mapbox', trip_status: 'planned',
  store: { latitude: '37.3352', longitude: '-121.8811' },
  destination: { latitude: '37.34', longitude: '-121.89' },
  vehicle_position: null, last_report: null, last_updated: null,
  directions_url: 'https://www.google.com/maps/dir/?api=1',
}
beforeEach(() => {
  vi.clearAllMocks()
  mapbox.state.maps.length = 0
  mapbox.state.markers.length = 0
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => ({ routes: [{ geometry: { coordinates: [[-121.8811, 37.3352], [-121.89, 37.34]] } }] }),
  }))
})
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

describe('delivery maps', () => {
  test('loads streets and a customer driving route with a directions link', async () => {
    render(<DeliveryMap trackingMap={planned} />)
    expect(screen.getByRole('region', { name: 'Delivery map' })).toBeInTheDocument()
    expect(mapbox.Map).toHaveBeenCalledWith(expect.objectContaining({ style: 'mapbox://styles/mapbox/streets-v12' }))
    await waitFor(() => expect(mapbox.state.maps[0].source.setData).toHaveBeenCalledWith(expect.objectContaining({
      features: [expect.objectContaining({ geometry: expect.objectContaining({ coordinates: [[-121.8811, 37.3352], [-121.89, 37.34]] }) })],
    })))
    expect(screen.getByRole('link', { name: 'Open route in Google Maps' })).toHaveAttribute('href', planned.directions_url)
  })

  test('routes from the reported vehicle position and moves its marker without rebuilding the map', async () => {
    const tracking = { ...planned, trip_status: 'out_for_delivery', last_report: 'en_route', vehicle_position: { latitude: '37.3361', longitude: '-121.8905' } }
    const { rerender } = render(<DeliveryMap trackingMap={tracking} />)
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('-121.8905,37.3361;-121.89,37.34'), expect.anything()))
    await waitFor(() => expect(mapbox.state.maps[0].source.setData).toHaveBeenCalledWith(expect.objectContaining({ features: [expect.anything()] })))
    const vehicle = mapbox.state.markers.find((marker) => marker.options.color === '#f59e0b')
    const map = mapbox.state.maps[0]
    const fitCount = map.fitBounds.mock.calls.length
    rerender(<DeliveryMap trackingMap={{ ...tracking, vehicle_position: { latitude: '37.337', longitude: '-121.889' } }} />)
    expect(mapbox.Map).toHaveBeenCalledTimes(1)
    expect(vehicle.setLngLat).toHaveBeenLastCalledWith([-121.889, 37.337])
    expect(map.fitBounds).toHaveBeenCalledTimes(fitCount)
    expect(fetch).toHaveBeenCalledTimes(1) // directions refresh is rate-limited
    fireEvent.click(screen.getByRole('checkbox', { name: 'Follow vehicle' }))
    expect(map.easeTo).toHaveBeenCalledWith(expect.objectContaining({ center: [-121.889, 37.337] }))
  })

  test('draws the manager road geometry in the correct coordinate order without another API lookup', async () => {
    render(<TripMap trip={{
      trip_id: 9, vehicle: { name: 'Robot 1' }, route_planned: true, status: 'planned',
      route: { provider: 'mapbox', store: planned.store, path: [[37.3352, -121.8811], [37.34, -121.89], [37.35, -121.88]] },
      stops: [{ order_id: 4, order_number: 'OFS-4', stop_sequence: 1, latitude: '37.34', longitude: '-121.89', delivered_at: null }],
      last_position: null,
    }} />)
    await waitFor(() => expect(mapbox.state.maps[0].addSource).toHaveBeenCalledWith('delivery-route', expect.objectContaining({
      data: expect.objectContaining({ features: [expect.objectContaining({ geometry: { type: 'LineString', coordinates: [[-121.8811, 37.3352], [-121.89, 37.34], [-121.88, 37.35]] } })] }),
    })))
    expect(fetch).not.toHaveBeenCalled()
    expect(mapbox.state.markers[1].options.element.textContent).toBe('1')
  })

  test('keeps markers and explains a failed route instead of drawing a false road route', async () => {
    fetch.mockResolvedValue({ ok: false, status: 503 })
    render(<DeliveryMap trackingMap={planned} />)
    expect(await screen.findByRole('status')).toHaveTextContent('road route is temporarily unavailable')
    expect(mapbox.state.markers).toHaveLength(2)
  })

  test('shows a clearly labeled diagram when no public token is configured', () => {
    vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', '')
    render(<DeliveryMap trackingMap={planned} />)
    expect(screen.getByRole('img', { name: 'Delivery route diagram' })).toBeInTheDocument()
    expect(screen.getByText(/approximate positions, not a road route/)).toBeInTheDocument()
    expect(mapbox.Map).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  test('explains missing coordinates and rejects null, blank, and out-of-range points', () => {
    render(<DeliveryMap trackingMap={{ ...planned, destination: null }} />)
    expect(screen.getByText(/map will appear when the store assigns a route/)).toBeInTheDocument()
    expect(mapPoint({ latitude: null, longitude: 0 })).toBeNull()
    expect(mapPoint({ latitude: '', longitude: 0 })).toBeNull()
    expect(mapPoint({ latitude: 100, longitude: 0 })).toBeNull()
    expect(mapPoint({ latitude: 0, longitude: 0 })).toEqual({ latitude: 0, longitude: 0 })
  })

  test('fits every stop and the vehicle using a proper two-corner bounding box', () => {
    expect(mapBounds([[-121.88, 37.33], [-121.9, 37.35], [-121.87, 37.32]])).toEqual([[-121.9, 37.32], [-121.87, 37.35]])
  })

  test('flags stale vehicle data and removes the vehicle marker once this order is delivered', () => {
    const tracking = { ...planned, last_report: 'en_route', vehicle_position: planned.store, last_updated: new Date(Date.now() - 180000).toISOString() }
    const { rerender } = render(<DeliveryMap trackingMap={tracking} />)
    expect(screen.getByText(/last report is over 2 minutes old/)).toBeInTheDocument()
    const vehicle = mapbox.state.markers.find((marker) => marker.options.color === '#f59e0b')
    rerender(<DeliveryMap trackingMap={tracking} status="delivered" />)
    expect(vehicle.remove).toHaveBeenCalled()
    expect(screen.queryByRole('checkbox', { name: 'Follow vehicle' })).not.toBeInTheDocument()
    expect(screen.queryByText(/last report is over 2 minutes old/)).not.toBeInTheDocument()
  })

  test('removes the map and markers on unmount', () => {
    const { unmount } = render(<DeliveryMap trackingMap={planned} />)
    const map = mapbox.state.maps[0]
    unmount()
    expect(map.remove).toHaveBeenCalledTimes(1)
    mapbox.state.markers.forEach((marker) => expect(marker.remove).toHaveBeenCalled())
  })

  test('loads the first road route under React StrictMode without a one-minute delay', async () => {
    render(<React.StrictMode><DeliveryMap trackingMap={planned} /></React.StrictMode>)
    await waitFor(() => expect(mapbox.state.maps.at(-1).source.setData).toHaveBeenCalledWith(expect.objectContaining({ features: [expect.anything()] })))
  })
})
