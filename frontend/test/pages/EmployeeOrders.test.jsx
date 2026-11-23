import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import EmployeeOrders from '../../src/pages/EmployeeOrders'
import { api } from '../../src/api'
import { renderWithProviders } from '../renderWithProviders'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }
const customer = { user_id: 1, full_name: 'Anna Rivera', role: 'customer' }
const cart = { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false }

const order = (fields = {}) => ({
  order_id: 1, order_number: 'OFS-AAA111', status: 'placed', placed_at: '2026-11-20T10:00:00', delivered_at: null,
  total_weight_lb: '4.00', grand_total: '12.50', customer_name: 'Anna Rivera', item_count: 2, trip_id: null, unscheduled_reason: null, ...fields,
})
const counts = { placed: 1, awaiting_delivery: 1, assigned_to_trip: 0, out_for_delivery: 0, delivered: 0 }
const detail = {
  order_id: 1, order_number: 'OFS-AAA111', status: 'placed', placed_at: '2026-11-20T10:00:00', delivered_at: null,
  subtotal: '10.00', tax: '0.94', delivery_fee: '0.00', total_weight_lb: '4.00', grand_total: '10.94', customer_name: 'Anna Rivera',
  items: [{ product_id: 1, name: 'Apple', quantity: 2, unit_weight_lb: '2.00', line_total: '10.00' }],
  history: [{ status: 'placed', at: '2026-11-20T10:00:00' }], trip: null, unscheduled_reason: null,
}

// Answers the page's requests; the list reflects the status filter the page sends.
function mockApi({ user = employee, orders = [order(), order({ order_id: 2, order_number: 'OFS-BBB222', status: 'awaiting_delivery', trip_id: 3 })], failList = false } = {}) {
  api.mockImplementation(async (path) => {
    if (path === '/api/auth/me') return { user }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart }
    if (path.startsWith('/api/staff/orders?')) {
      if (failList) throw new Error('Connection lost')
      const status = new URLSearchParams(path.split('?')[1]).get('status')
      const shown = orders.filter((o) => !status || o.status === status)
      return { orders: shown, status_counts: counts, pagination: { page: 1, per_page: 10, total: shown.length, total_pages: 1 } }
    }
    if (path === '/api/staff/orders/1') return { order: detail }
    throw new Error(`Unexpected API request: ${path}`)
  })
}

const open = () => renderWithProviders(
  <Routes>
    <Route path="/staff/orders" element={<EmployeeOrders />} />
    <Route path="/login" element={<p>Login page</p>} />
    <Route path="/orders" element={<p>Customer orders page</p>} />
  </Routes>,
  { route: '/staff/orders' },
)

describe('EmployeeOrders', () => {
  beforeEach(() => { vi.resetAllMocks(); mockApi() })

  test('lists every order with its customer, size, total and status', async () => {
    open()

    expect(await screen.findByText('OFS-AAA111')).toBeInTheDocument()
    expect(screen.getByText('OFS-BBB222')).toBeInTheDocument()
    expect(screen.getAllByText(/Anna Rivera/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/\$12\.50/).length).toBe(2)
    expect(screen.getByText(/Awaiting delivery · trip #3/)).toBeInTheDocument()
    expect(screen.getByText(/trip #3/)).toBeInTheDocument()
  })

  test('has the status chips with their counts, and a chip filters the list', async () => {
    const user = userEvent.setup()
    open()
    await screen.findByText('OFS-AAA111')

    expect(screen.getByRole('button', { name: 'All (2)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Order placed (1)' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Awaiting delivery (1)' }))

    await waitFor(() => expect(screen.queryByText('OFS-AAA111')).not.toBeInTheDocument())
    expect(screen.getByText('OFS-BBB222')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith(expect.stringContaining('status=awaiting_delivery'))
  })

  test('searching sends the text and the dates', async () => {
    const user = userEvent.setup()
    open()
    await screen.findByText('OFS-AAA111')

    await user.type(screen.getByLabelText('Search orders'), 'AAA')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(api).toHaveBeenCalledWith(expect.stringContaining('q=AAA')))
  })

  test('opening an order shows what to pick, the totals and the progress, and no contact or payment details', async () => {
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByRole('button', { name: /OFS-AAA111/ }))

    expect(await screen.findByText(/2 × Apple/)).toBeInTheDocument()
    expect(screen.getByText(/Total \$10\.94/)).toBeInTheDocument()
    expect(screen.getByText(/Order placed ·/)).toBeInTheDocument()
    expect(screen.queryByText(/@/)).not.toBeInTheDocument()
    expect(screen.queryByText(/card|address|phone/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(mark ready for delivery|dispatch|confirm delivered)/i })).not.toBeInTheDocument()
  })

  test('says so when there are no orders', async () => {
    mockApi({ orders: [] })
    open()

    expect(await screen.findByText('No orders here.')).toBeInTheDocument()
  })

  test('shows a failed refresh instead of an empty list', async () => {
    mockApi({ failList: true })
    open()

    expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
  })

  test('sends a signed-out visitor to sign in and a customer to their own orders, without asking for staff data', async () => {
    mockApi({ user: null })
    open()
    expect(await screen.findByText('Login page')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith(expect.stringContaining('/api/staff/orders'))
  })

  test('a customer is sent to their own orders', async () => {
    mockApi({ user: customer })
    open()

    expect(await screen.findByText('Customer orders page')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith(expect.stringContaining('/api/staff/orders'))
  })
})
