import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import AdminOrders from './AdminOrders'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))

const manager = { user_id: 3, full_name: 'Mia Chen', role: 'manager' }
const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }

const emptyCart = {
  items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00',
  delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false,
}

// The fake backend keeps one order. Status changes move it along, like
// the real database, and refuse anything but the next step.
const nextStatus = {
  placed: 'awaiting_delivery',
  awaiting_delivery: 'assigned_to_trip',
  assigned_to_trip: 'out_for_delivery',
  out_for_delivery: 'delivered',
  delivered: null,
}

let order

const summary = () => ({
  order_id: 7,
  order_number: 'OFS-1007',
  status: order.status,
  placed_at: '2026-10-20T10:00:00',
  grand_total: '27.35',
  total_weight_lb: '6.00',
  customer_name: 'Anna Rivera',
  customer_email: 'anna@example.com',
  item_count: 6,
  trip_id: order.trip_id,
  unscheduled_reason: order.unscheduled_reason,
})

const detail = () => ({
  ...summary(),
  subtotal: '25.00',
  tax: '2.35',
  delivery_fee: '0.00',
  customer: { user_id: 1, full_name: 'Anna Rivera', email: 'anna@example.com', phone: null },
  address: { street: '1 Washington Sq', city: 'San Jose', state: 'CA', zip_code: '95192' },
  items: [{ product_id: 1, name: 'Apple', quantity: 6, unit_price: '2.50', line_total: '15.00' }],
  history: [{ to_status: 'placed', changed_at: '2026-10-20T10:00:00', changed_by: 'Anna Rivera' }],
  trip: null,
  next_status: nextStatus[order.status],
})

function mockApi(signedInUser = manager, fields = {}) {
  order = { status: 'placed', trip_id: null, unscheduled_reason: null, ...fields }
  api.mockImplementation(async (path, options = {}) => {
    const { method = 'GET', body } = options

    if (path === '/api/auth/me') return { user: signedInUser }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }

    if (path === '/api/admin/orders/7/status' && method === 'PATCH') {
      if (body.status !== nextStatus[order.status]) {
        throw new Error(`An order cannot go from ${order.status} to ${body.status}.`)
      }
      order.status = body.status
      return { order: summary() }
    }
    if (path === '/api/admin/orders/7/payments') {
      return { payments: [{ transaction_id: 1, amount: '27.35', status: 'approved', card_last4: '4242', failure_reason: null }] }
    }
    if (path === '/api/admin/orders/7') return { order: detail() }
    if (path.startsWith('/api/admin/orders?')) return { orders: [summary()] }

    throw new Error(`Unexpected API request: ${method} ${path}`)
  })
}

const openOrder = async (user) => {
  await user.click(await screen.findByText('OFS-1007'))
  await screen.findByText('Deliver to')
}

describe('AdminOrders', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('lists each order with its customer, total and status', async () => {
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })

    const row = await screen.findByRole('button', { name: /OFS-1007/ })
    expect(row).toHaveTextContent('Anna Rivera')
    expect(row).toHaveTextContent('$27.35')
    expect(row).toHaveTextContent('Order placed')
  })

  test('filtering by status and date asks the backend for just those orders', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })
    await screen.findByText('OFS-1007')

    await user.selectOptions(screen.getByLabelText('Status'), 'awaiting_delivery')
    await user.type(screen.getByLabelText('From date'), '2026-10-01')

    expect(api).toHaveBeenCalledWith('/api/admin/orders?status=awaiting_delivery&from=2026-10-01')
  })

  test('opening an order shows its items, address and payments', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })

    await openOrder(user)

    expect(screen.getByText('6 × Apple')).toBeInTheDocument()
    expect(screen.getByText(/1 Washington Sq/)).toBeInTheDocument()
    expect(screen.getByText(/card ending 4242/)).toBeInTheDocument()
  })

  test('marking a placed order ready moves it to awaiting delivery', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })
    await openOrder(user)

    await user.click(screen.getByRole('button', { name: 'MARK READY FOR DELIVERY' }))

    expect(api).toHaveBeenCalledWith('/api/admin/orders/7/status', {
      method: 'PATCH',
      body: { status: 'awaiting_delivery' },
    })
    expect(await screen.findByText('Next step: add this order to a delivery trip.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'MARK READY FOR DELIVERY' })).not.toBeInTheDocument()
  })

  test('an order out for delivery can be confirmed as delivered', async () => {
    mockApi(manager, { status: 'out_for_delivery', trip_id: 4 })
    const user = userEvent.setup()
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })
    await openOrder(user)

    await user.click(screen.getByRole('button', { name: 'CONFIRM DELIVERED' }))

    expect(api).toHaveBeenCalledWith('/api/admin/orders/7/status', {
      method: 'PATCH',
      body: { status: 'delivered' },
    })
    expect(await screen.findAllByText('Delivered')).not.toHaveLength(0)
  })

  test('flags orders that could not be scheduled', async () => {
    mockApi(manager, { status: 'awaiting_delivery', unscheduled_reason: 'Too heavy for one vehicle' })
    renderWithProviders(<AdminOrders />, { route: '/admin/orders' })

    expect(await screen.findByText('NEEDS ATTENTION')).toBeInTheDocument()
  })

  test('sends anyone who is not a manager to sign in', async () => {
    mockApi(employee)
    renderWithProviders(
      <Routes>
        <Route path="/admin/orders" element={<AdminOrders />} />
        <Route path="/login" element={<p>Sign in page</p>} />
      </Routes>,
      { route: '/admin/orders' }
    )

    expect(await screen.findByText('Sign in page')).toBeInTheDocument()
  })
})
