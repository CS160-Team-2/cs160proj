import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { ManagerDelivery, ManagerOrders } from './Manager'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))
beforeEach(() => vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', ''))
afterEach(() => vi.unstubAllEnvs())

const manager = { user_id: 3, full_name: 'Mia Chen', role: 'manager' }
const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }
const customer = { user_id: 1, full_name: 'Anna Rivera', role: 'customer' }

const emptyCart = {
  items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00',
  delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false,
}

const order = (fields) => ({
  order_id: 1,
  order_number: 'OFS-0001',
  status: 'placed',
  customer_name: 'Anna Rivera',
  placed_at: '2026-10-20T10:00:00',
  item_count: 2,
  total_weight_lb: '5.00',
  grand_total: '20.00',
  trip_id: null,
  unscheduled_reason: null,
  ...fields,
})

const orderDetail = {
  order_id: 1,
  order_number: 'OFS-0001',
  status: 'placed',
  subtotal: '18.00',
  tax: '1.50',
  delivery_fee: '0.00',
  items: [{ product_id: 1, name: 'Apple', quantity: 3, unit_price: '2.50', unit_weight_lb: '1.00', line_total: '7.50' }],
  customer: { full_name: 'Anna Rivera', email: 'anna@example.com', phone: null },
  address: { street: '1 Main St', city: 'San Jose', state: 'CA', zip_code: '95112' },
  payment: { card_last4: '4242', status: 'approved' },
  history: [{ from_status: null, to_status: 'placed', source: 'customer', changed_at: '2026-10-20T10:00:00', changed_by: null }],
}

const robot = (fields) => ({
  vehicle_id: 1, name: 'Robot 1', max_orders: 10, max_weight_lb: '200.00',
  status: 'available', current_trip_id: null, ...fields,
})

const waiting = (fields) => ({
  order_id: 3, order_number: 'OFS-0003', total_weight_lb: '120.00',
  placed_at: '2026-10-20T10:00:00', unscheduled_reason: null, waited_minutes: 12, ...fields,
})

const trip = (fields) => ({
  trip_id: 1,
  status: 'planned',
  vehicle: { vehicle_id: 1, name: 'Robot 1', max_orders: 10, max_weight_lb: '200.00' },
  order_count: 1,
  total_weight_lb: '10.00',
  remaining_orders: 9,
  remaining_weight_lb: '190.00',
  capacity_problem: null,
  route_planned: true,
  route: { provider: 'fake', store: { latitude: '37.33', longitude: '-121.88' }, path: [], total_minutes: 12 },
  stops: [{
    order_id: 4, order_number: 'OFS-0004', status: 'assigned_to_trip', customer_name: 'Ben Cho',
    address: '2 Oak St, San Jose, CA 95113', latitude: '37.34', longitude: '-121.89',
    weight_lb: '10.00', stop_sequence: 1, est_arrival: null, delivered_at: null,
  }],
  created_at: '2026-10-20T10:00:00',
  started_at: null,
  completed_at: null,
  last_report: null,
  last_position: null,
  ...fields,
})

// What the fake backend currently holds; each test sets what it needs.
let data

function mockApi(signedInUser = manager) {
  data = { orders: [order()], detail: orderDetail, queue: [], exceptions: [], vehicles: [robot()], trips: [] }
  api.mockImplementation(async (path, options = {}) => {
    const { method = 'GET' } = options

    if (path === '/api/auth/me') return { user: signedInUser }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }

    if (path === '/api/admin/orders') return { orders: data.orders }
    if (path === '/api/admin/orders/1' && method === 'GET') return { order: data.detail }
    if (path === '/api/admin/orders/1/tracking') return { map: null, estimated_arrival: null }
    if (path.startsWith('/api/admin/orders/') && method === 'PATCH') return { order: order() }

    if (path === '/api/admin/delivery/queue') return { orders: data.queue }
    if (path === '/api/admin/delivery/exceptions') return { orders: data.exceptions }
    if (path === '/api/admin/delivery/vehicles') return { vehicles: data.vehicles }
    if (path === '/api/admin/delivery/trips' && method === 'GET') return { trips: data.trips }
    if (path === '/api/admin/delivery/trips' && method === 'POST') {
      return { trip: trip({ trip_id: 7, order_count: 1 }), route_error: null }
    }
    if (path.startsWith('/api/admin/delivery/trips/')) return { trip: trip(), route_error: null }

    throw new Error(`Unexpected API request: ${method} ${path}`)
  })
}

describe('ManagerOrders', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('lists every order with a count for each status', async () => {
    data.orders = [order(), order({ order_id: 2, order_number: 'OFS-0002', status: 'awaiting_delivery' })]
    renderWithProviders(<ManagerOrders />, { route: '/manager' })

    expect(await screen.findByText('OFS-0001')).toBeInTheDocument()
    expect(screen.getByText('OFS-0002')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All (2)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Order placed (1)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delivered (0)' })).toBeInTheDocument()
  })

  test('filters the list by status', async () => {
    const user = userEvent.setup()
    data.orders = [order(), order({ order_id: 2, order_number: 'OFS-0002', status: 'awaiting_delivery' })]
    renderWithProviders(<ManagerOrders />, { route: '/manager' })
    await screen.findByText('OFS-0001')

    await user.click(screen.getByRole('button', { name: 'Awaiting delivery (1)' }))

    expect(screen.queryByText('OFS-0001')).not.toBeInTheDocument()
    expect(screen.getByText('OFS-0002')).toBeInTheDocument()
  })

  test('marks a placed order ready for delivery', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerOrders />, { route: '/manager' })
    await screen.findByText('OFS-0001')

    await user.click(screen.getByRole('button', { name: 'MARK READY FOR DELIVERY' }))

    expect(api).toHaveBeenCalledWith('/api/admin/orders/1/status', {
      method: 'PATCH',
      body: { status: 'awaiting_delivery' },
    })
  })

  test('opening an order shows its items, address and payment', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerOrders />, { route: '/manager' })
    await screen.findByText('OFS-0001')

    await user.click(screen.getByRole('button', { name: /OFS-0001/ }))

    expect(await screen.findByText(/3 × Apple/)).toBeInTheDocument()
    expect(screen.getByText(/1 Main St, San Jose, CA 95112/)).toBeInTheDocument()
    expect(screen.getByText('Paid with a card ending 4242')).toBeInTheDocument()
  })

  test('labels a guest and shows the email they gave at checkout', async () => {
    data.detail = {
      ...orderDetail,
      customer: { full_name: 'Grace Hopper', email: 'grace@example.com', phone: null, is_guest: true },
    }
    const user = userEvent.setup()
    renderWithProviders(<ManagerOrders />, { route: '/manager' })
    await screen.findByText('OFS-0001')

    await user.click(screen.getByRole('button', { name: /OFS-0001/ }))

    expect(await screen.findByText(/Grace Hopper \(guest checkout\) · grace@example\.com/)).toBeInTheDocument()
  })

  test('shows why an order was not scheduled', async () => {
    data.orders = [order({ status: 'awaiting_delivery', unscheduled_reason: 'Too heavy for the vehicle' })]
    renderWithProviders(<ManagerOrders />, { route: '/manager' })

    expect(await screen.findByText('Not scheduled: Too heavy for the vehicle')).toBeInTheDocument()
  })

  test('sends an employee to the inventory and a customer home', async () => {
    mockApi(employee)
    const { unmount } = renderWithProviders(
      <Routes>
        <Route path="/manager" element={<ManagerOrders />} />
        <Route path="/inventory" element={<p>Inventory page</p>} />
      </Routes>,
      { route: '/manager' }
    )
    expect(await screen.findByText('Inventory page')).toBeInTheDocument()
    unmount()

    mockApi(customer)
    renderWithProviders(
      <Routes>
        <Route path="/manager" element={<ManagerOrders />} />
        <Route path="/" element={<p>Home page</p>} />
      </Routes>,
      { route: '/manager' }
    )
    expect(await screen.findByText('Home page')).toBeInTheDocument()
  })
})

describe('ManagerDelivery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('lists orders that cannot be scheduled, with the reason', async () => {
    data.exceptions = [{
      order_id: 5, order_number: 'OFS-0005', total_weight_lb: '250.00',
      reason: 'Too heavy for the vehicle: 250.00 lb, limit 200.00 lb',
    }]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })

    expect(await screen.findByText('Too heavy for the vehicle: 250.00 lb, limit 200.00 lb', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('OFS-0005')).toBeInTheDocument()
  })

  test('blocks a trip that goes over the vehicle weight limit', async () => {
    const user = userEvent.setup()
    data.queue = [waiting(), waiting({ order_id: 4, order_number: 'OFS-0004' })]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })
    await screen.findByText('OFS-0003')

    await user.click(screen.getByLabelText('Select OFS-0003'))
    expect(screen.getByRole('button', { name: 'CREATE TRIP FROM SELECTED' })).toBeEnabled()

    await user.click(screen.getByLabelText('Select OFS-0004'))
    expect(screen.getByText('Trip weighs 240 lb; the vehicle limit is 200 lb')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CREATE TRIP FROM SELECTED' })).toBeDisabled()
  })

  test('creates a trip from the selected orders', async () => {
    const user = userEvent.setup()
    data.queue = [waiting()]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })
    await screen.findByText('OFS-0003')

    await user.click(screen.getByLabelText('Select OFS-0003'))
    await user.click(screen.getByRole('button', { name: 'CREATE TRIP FROM SELECTED' }))

    expect(await screen.findByText('Trip #7 was created with 1 orders.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/delivery/trips', {
      method: 'POST',
      body: { vehicle_id: 1, order_ids: [3] },
    })
  })

  test('shows a trip with its stops, then dispatches it', async () => {
    const user = userEvent.setup()
    data.trips = [trip()]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })

    expect(await screen.findByText(/OFS-0004/, { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText(/Ben Cho/)).toBeInTheDocument()
    expect(screen.getByText(/Route planned with the offline demo provider/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'DISPATCH' }))

    expect(api).toHaveBeenCalledWith('/api/admin/delivery/trips/1/dispatch', { method: 'POST' })
  })

  test('removes a stop from a planned trip', async () => {
    const user = userEvent.setup()
    data.trips = [trip()]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })
    await screen.findByText(/OFS-0004/, { selector: 'span' })

    await user.click(screen.getByRole('button', { name: 'Remove OFS-0004 from trip 1' }))

    expect(api).toHaveBeenCalledWith('/api/admin/delivery/trips/1/orders/4', { method: 'DELETE' })
  })

  test('cannot dispatch a trip that has no route', async () => {
    data.trips = [trip({ route_planned: false, route: null })]
    renderWithProviders(<ManagerDelivery />, { route: '/manager/delivery' })

    expect(await screen.findByText(/No route planned yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'DISPATCH' })).toBeDisabled()
  })
})
