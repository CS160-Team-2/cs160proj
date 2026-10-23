import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DeliveryMap from './DeliveryMap'

const mapbox = vi.hoisted(() => {
  const state = { maps: [], markers: [] }

  const Map = vi.fn(() => {
    const instance = {
      addControl: vi.fn(),
      addSource: vi.fn(),
      addLayer: vi.fn(),
      fitBounds: vi.fn(),
      on: vi.fn((event, callback) => {
        if (event === 'load') Promise.resolve().then(callback)
        return instance
      }),
      remove: vi.fn(),
    }
    state.maps.push(instance)
    return instance
  })

  const Marker = vi.fn((options) => {
    const instance = {
      options,
      setLngLat: vi.fn(() => instance),
      setPopup: vi.fn(() => instance),
      addTo: vi.fn(() => instance),
      remove: vi.fn(),
    }
    state.markers.push(instance)
    return instance
  })

  const Popup = vi.fn(() => {
    const instance = { setText: vi.fn(() => instance) }
    return instance
  })

  return { state, Map, Marker, Popup, NavigationControl: vi.fn() }
})

vi.mock('mapbox-gl', () => ({
  default: {
    accessToken: '',
    Map: mapbox.Map,
    Marker: mapbox.Marker,
    Popup: mapbox.Popup,
    NavigationControl: mapbox.NavigationControl,
  },
}))

const planned = {
  provider: 'mapbox',
  trip_status: 'planned',
  store: { latitude: '37.335200', longitude: '-121.881100' },
  destination: { latitude: '37.340000', longitude: '-121.890000' },
  vehicle_position: null,
  last_report: null,
  last_updated: null,
  directions_url: 'https://www.google.com/maps/dir/?api=1&origin=37.3352%2C-121.8811&destination=37.34%2C-121.89&travelmode=driving',
}

beforeEach(() => {
  mapbox.state.maps.length = 0
  mapbox.state.markers.length = 0
  mapbox.Map.mockClear()
  mapbox.Marker.mockClear()
  mapbox.Popup.mockClear()
  mapbox.NavigationControl.mockClear()
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('DeliveryMap', () => {
  test('loads an interactive Mapbox street map and driving route', async () => {
    vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        routes: [{ geometry: { coordinates: [[-121.8811, 37.3352], [-121.89, 37.34]] } }],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<DeliveryMap trackingMap={planned} />)

    expect(screen.getByRole('region', { name: 'Delivery map' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /interactive delivery street map/i })).toBeInTheDocument()
    expect(screen.getByText('Route planned with Mapbox.')).toBeInTheDocument()
    expect(mapbox.Map).toHaveBeenCalledWith(expect.objectContaining({
      style: 'mapbox://styles/mapbox/streets-v12',
    }))
    expect(mapbox.Marker).toHaveBeenCalledTimes(2)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('api.mapbox.com/directions/v5/mapbox/driving'),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await waitFor(() => expect(mapbox.state.maps[0].addSource).toHaveBeenCalledWith(
      'delivery-route',
      expect.objectContaining({ type: 'geojson' }),
    ))
    expect(mapbox.state.maps[0].addLayer).toHaveBeenCalledWith(expect.objectContaining({
      id: 'delivery-route-line',
    }))
    expect(screen.getByRole('link', { name: 'Open route in Google Maps' })).toHaveAttribute(
      'href', planned.directions_url,
    )
  })

  test('adds a live vehicle marker and displays the latest report', () => {
    vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ routes: [] }) }))

    render(<DeliveryMap trackingMap={{
      ...planned,
      trip_status: 'out_for_delivery',
      vehicle_position: { latitude: '37.336100', longitude: '-121.890500' },
      last_report: 'en_route',
      last_updated: '2026-10-22T17:30:00Z',
    }} />)

    expect(mapbox.Marker).toHaveBeenCalledTimes(3)
    expect(mapbox.state.markers[2].options).toEqual({ color: '#f59e0b' })
    expect(screen.getByText(/Latest vehicle report:/)).toHaveTextContent('en_route')
    expect(screen.queryByText(/live vehicle marker will appear/i)).not.toBeInTheDocument()
  })

  test('keeps the schematic fallback when no browser token is configured', () => {
    vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', '')

    render(<DeliveryMap trackingMap={planned} />)

    expect(screen.getByRole('img', { name: /delivery route/i })).toBeInTheDocument()
    expect(screen.getByText(/add VITE_MAPBOX_ACCESS_TOKEN/i)).toBeInTheDocument()
    expect(mapbox.Map).not.toHaveBeenCalled()
  })

  test('renders nothing until valid map coordinates exist', () => {
    vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', 'pk.test-token')
    const { container } = render(
      <DeliveryMap trackingMap={{ ...planned, destination: null }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
