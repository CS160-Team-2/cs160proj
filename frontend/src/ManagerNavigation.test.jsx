import React from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import App from './App'
import { api } from './api'
import { renderWithProviders } from './test/renderWithProviders'

vi.mock('./api', () => ({ api: vi.fn() }))

const tabs = [
  ['Orders', '/manager'], ['Delivery', '/manager/delivery'],
  ['Problems', '/manager/problems'], ['Vehicles', '/manager/vehicles'],
  ['Staff', '/manager/staff'], ['Inventory', '/inventory'],
]
const vehicle = { vehicle_id: 1, name: 'Robot 1', max_orders: 10, max_weight_lb: '200.00', status: 'available', current_trip_id: null }
const makeTrip = (trip_id) => ({
  trip_id, vehicle, status: 'planned', vehicle_mode: 'simulated',
  order_count: 0, total_weight_lb: '0.00', route_planned: false,
  stops: [], route: null, created_at: '2026-11-18T10:00:00',
})
let account, stock

beforeEach(() => {
  vi.resetAllMocks()
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.stubEnv('VITE_MAPBOX_ACCESS_TOKEN', '')
  account = { user_id: 3, full_name: 'Emily Manager', role: 'manager', is_active: true }
  stock = 5
  api.mockImplementation(async (path, options = {}) => {
    const url = new URL(path, 'http://localhost')
    if (path === '/api/auth/me') return { user: account }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: { items: [], item_count: 0 } }
    if (path === '/api/categories') return { categories: ['Fruits'] }
    if (path === '/api/admin/inventory/1' && options.method === 'PATCH') {
      stock += options.body.delta
      return { product: { product_id: 1, stock } }
    }
    if (url.pathname === '/api/admin/inventory') return { inventory: [{
      product_id: 1, name: 'Apple', category: 'Fruits', price: '2.50',
      unit_weight_lb: '1.00', stock, is_listed: true, available: true, low_stock: false,
    }] }
    if (url.pathname === '/api/admin/orders') return {
      orders: [], status_counts: {}, pagination: { page: 1, per_page: 25, total: 0, total_pages: 1 },
    }
    if (path === '/api/admin/delivery/queue' || path === '/api/admin/delivery/exceptions') return { orders: [] }
    if (path === '/api/admin/delivery/vehicles') return { vehicles: [vehicle] }
    if (path === '/api/admin/delivery/trips' || path === '/api/staff/delivery/trips') return { trips: [makeTrip(1), makeTrip(7)] }
    if (path === '/api/admin/delivery/trips/7') return { trip: makeTrip(7) }
    if (path === '/api/admin/staff') return { staff: [account] }
    if (url.pathname === '/api/admin/problems') return {
      problems: [], pagination: { page: 1, per_page: 25, total: 0, total_pages: 1 },
    }
    throw new Error(`Unexpected request: ${path}`)
  })
})

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs() })

function Location() {
  const { pathname, search, hash } = useLocation()
  return <output data-testid="location">{pathname}{search}{hash}</output>
}

function openApp(route) {
  return renderWithProviders(<><App /><Location /></>, { route })
}

async function expectTabs(active) {
  const nav = await screen.findByRole('navigation', { name: 'Manager pages' })
  const links = within(nav).getAllByRole('link')
  expect(links.map((link) => [link.textContent, link.getAttribute('href')])).toEqual(tabs)
  expect(links.filter((link) => link.getAttribute('aria-current') === 'page').map((link) => link.textContent)).toEqual([active])
  return within(nav)
}

test('managers can switch from Inventory through every manager tab and back', async () => {
  const user = userEvent.setup()
  openApp('/inventory')
  await screen.findByText('Apple', { exact: true })
  await expectTabs('Inventory')
  expect(screen.getByLabelText('Delivery manifest file')).toBeInTheDocument()

  let active = 'Inventory'
  for (const [label, path] of tabs) {
    const nav = await expectTabs(active)
    await user.click(nav.getByRole('link', { name: label, exact: true }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(new RegExp(`^${path}$`)))
    await expectTabs(label)
    const checks = {
      Orders: () => screen.findByRole('searchbox', { name: 'Search orders' }),
      Delivery: () => screen.findByText('NEW TRIP', { exact: true }),
      Problems: () => screen.findByText('No problems match these filters.'),
      Vehicles: () => screen.findByText('Robot 1', { exact: true }),
      Staff: () => screen.findByText('Emily Manager', { exact: true }),
      Inventory: () => screen.findByText('Apple', { exact: true }),
    }
    await checks[label]()
    active = label
  }
  expect(screen.getByLabelText('Delivery manifest file')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('manager Inventory still updates stock with the shared tabs present', async () => {
  const user = userEvent.setup()
  openApp('/inventory')
  const input = await screen.findByRole('spinbutton', { name: 'Change stock of Apple' })
  await user.type(input, '3')
  await user.click(screen.getByRole('button', { name: 'UPDATE', exact: true }))
  await waitFor(() => expect(screen.getByText(/In stock:/)).toHaveTextContent('In stock: 8'))
  expect(api).toHaveBeenCalledWith('/api/admin/inventory/1', { method: 'PATCH', body: { delta: 3, reason: 'Restock' } })
  await expectTabs('Inventory')
})

test('manager tracking links use the Delivery dashboard and preserve a legacy trip link', async () => {
  const user = userEvent.setup()
  openApp('/delivery?trip=7#trip-7')
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/manager/delivery?trip=7#trip-7'))
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Delivery trip', exact: true })).toHaveValue('7'))
  await expectTabs('Delivery')
  expect(screen.getByRole('heading', { name: 'Trip #7 route · Robot 1' })).toBeInTheDocument()
  expect(api).not.toHaveBeenCalledWith('/api/staff/delivery/trips')

  await user.click(screen.getByRole('button', { name: 'Account menu' }))
  expect(screen.getByRole('link', { name: 'Delivery tracking', exact: true })).toHaveAttribute('href', '/manager/delivery')
  await user.click(screen.getByRole('link', { name: 'Delivery tracking', exact: true }))
  await expectTabs('Delivery')
})

test('Delivery stays selected on a trip stop list and Inventory is one click away', async () => {
  const user = userEvent.setup()
  openApp('/manager/delivery/trips/7/manifest')
  await screen.findByRole('heading', { name: 'Trip #7 stop list' })
  const nav = await expectTabs('Delivery')
  expect(screen.getByRole('button', { name: 'Print stop list' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Download stops CSV' })).toBeInTheDocument()
  await user.click(nav.getByRole('link', { name: 'Inventory', exact: true }))
  await screen.findByText('Apple', { exact: true })
  await expectTabs('Inventory')
})

test('employees retain Inventory and read-only tracking without manager tabs or CSV upload', async () => {
  account = { ...account, user_id: 2, role: 'employee' }
  const user = userEvent.setup()
  openApp('/inventory')
  await screen.findByText('Apple', { exact: true })
  expect(screen.queryByRole('navigation', { name: 'Manager pages' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Delivery manifest file')).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'View delivery tracking' }))
  await screen.findByRole('combobox', { name: 'Delivery trip', exact: true })
  expect(screen.getByTestId('location')).toHaveTextContent(/^\/delivery$/)
  expect(screen.queryByRole('navigation', { name: 'Manager pages' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'DISPATCH', exact: true })).not.toBeInTheDocument()
  expect(api).toHaveBeenCalledWith('/api/staff/delivery/trips')
  expect(api.mock.calls.some(([path]) => path.startsWith('/api/admin/delivery/'))).toBe(false)
  await user.click(screen.getByRole('link', { name: 'Inventory', exact: true }))
  await screen.findByText('Apple', { exact: true })
})
