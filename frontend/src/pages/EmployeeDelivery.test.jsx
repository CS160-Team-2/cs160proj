import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import EmployeeDelivery from './EmployeeDelivery'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))
const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }
const cart = { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false }

const emptyBoard = { waiting: [], problems: [], vehicles: [] }

// Answers the page's requests for the given user, trips and board (waiting orders, problems, vehicles).
const mockAccount = (user, trips = [], board = emptyBoard) => {
  api.mockImplementation(async (path) => {
    if (path === '/api/auth/me') return { user }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart }
    if (path === '/api/staff/delivery/trips') return { trips }
    if (path === '/api/staff/delivery/board') return board
    throw new Error(`Unexpected path ${path}`)
  })
}
beforeEach(() => { vi.resetAllMocks(); vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', ''); mockAccount(employee) })
afterEach(() => vi.unstubAllEnvs())

describe('EmployeeDelivery', () => {
  test('loads the read-only staff endpoint and explains an empty fleet', async () => {
    renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })
    expect(await screen.findByText(/There are no delivery trips yet/)).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/staff/delivery/trips')
    expect(screen.queryByRole('button', { name: /dispatch/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory')
  })

  test('shows the selected trip and numbered delivery stops', async () => {
    mockAccount(employee, [{ trip_id: 7, status: 'out_for_delivery', vehicle: { name: 'Robot 1' }, total_weight_lb: '4.00', route_planned: true,
      route: { provider: 'fake', store: { latitude: '37.33', longitude: '-121.88' }, path: [[37.33, -121.88], [37.34, -121.89]] },
      stops: [{ order_id: 3, order_number: 'OFS-123', latitude: '37.34', longitude: '-121.89', stop_sequence: 1, delivered_at: null }], last_position: null }])
    renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })
    expect(await screen.findByRole('combobox', { name: 'Delivery trip' })).toBeInTheDocument()
    expect(screen.getByText('OFS-123')).toBeInTheDocument()
    expect(screen.getByText(/0 of 1 stops delivered/)).toBeInTheDocument()
  })

  test('shows the waiting orders, the vehicles and where each vehicle is', async () => {
    mockAccount(employee, [], {
      waiting: [{ order_number: 'OFS-WAIT01', total_weight_lb: '4.00', placed_at: '2026-11-18T10:00:00', waited_minutes: 12 }],
      problems: [],
      vehicles: [
        { vehicle_id: 1, name: 'Robot 1', max_orders: 10, max_weight_lb: '200.00', status: 'available', current_trip_id: null },
        { vehicle_id: 2, name: 'Robot 2', max_orders: 10, max_weight_lb: '200.00', status: 'on_trip', current_trip_id: 5 },
      ],
    })
    renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })

    const waiting = await screen.findByRole('list', { name: 'Orders waiting for delivery' })
    expect(waiting).toHaveTextContent('OFS-WAIT01')
    expect(waiting).toHaveTextContent('Waiting 12 min for a trip')
    const vehicles = screen.getByRole('list', { name: 'Delivery vehicles' })
    expect(vehicles).toHaveTextContent('Robot 1')
    expect(vehicles).toHaveTextContent('Up to 10 orders and 200.00 lb')
    expect(vehicles).toHaveTextContent('Available')
    expect(vehicles).toHaveTextContent('On trip #5')
  })

  test('says so when nothing is waiting and lists orders that cannot be scheduled with the reason', async () => {
    mockAccount(employee)
    const { unmount } = renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })
    expect(await screen.findByText(/No orders are waiting/)).toBeInTheDocument()
    expect(screen.queryByText(/cannot be scheduled right now/)).not.toBeInTheDocument()
    unmount()

    mockAccount(employee, [], { waiting: [], problems: [{ order_number: 'OFS-BAD01', total_weight_lb: '9.00', reason: 'Address could not be found' }], vehicles: [] })
    renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })
    expect(await screen.findByText(/cannot be scheduled right now/)).toBeInTheDocument()
    expect(screen.getByText(/Address could not be found/)).toBeInTheDocument()
  })

  test('redirects customers without requesting the staff fleet', async () => {
    mockAccount({ ...employee, role: 'customer' })
    renderWithProviders(<Routes><Route path="/delivery" element={<EmployeeDelivery />} /><Route path="/orders" element={<p>Customer orders</p>} /></Routes>, { route: '/delivery' })
    expect(await screen.findByText('Customer orders')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/staff/delivery/trips')
    expect(api).not.toHaveBeenCalledWith('/api/staff/delivery/board')
  })

  test('shows a failed refresh instead of claiming there are no trips', async () => {
    const fallback = api.getMockImplementation()
    api.mockImplementation((path, ...args) => path === '/api/staff/delivery/trips' ? Promise.reject(new Error('Connection lost')) : fallback(path, ...args))
    renderWithProviders(<EmployeeDelivery />, { route: '/delivery' })
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
    expect(screen.queryByText(/There are no delivery trips yet/)).not.toBeInTheDocument()
  })
})
