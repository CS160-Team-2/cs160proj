// test customer order pages:  show order list
// findByText() - wait for the text to appear
// getByText() - check if the text is there

import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OrderDetail, OrderHistory } from './Orders'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'

vi.mock('../api', () => ({ api: vi.fn() }))

const customer =
{
  user_id: 1,
  full_name: 'Anna Rivera',
  role: 'customer'
}

const orderInList =
{
  order_number: 'OFS-TEST001',
  placed_at: '2026-10-20T18:00:00Z',
  item_count: 2,
  status: 'out_for_delivery',
  grand_total: '9.75'
}

const orderDetails =
{
  order_number: 'OFS-TEST001',
  placed_at: '2026-10-20T18:00:00Z',
  items: [
    { product_id: 1, name: 'Apple', quantity: 2, line_total: '5.00' }
  ],
  address:
  {
    street: '1 Washington Sq',
    city: 'San Jose',
    state: 'CA',
    zip_code: '95192'
  },
  payment: { card_last4: '4242' },
  subtotal: '5.00',
  total_weight_lb: '2.00',
  delivery_fee: '0.00',
  tax: '0.50',
  grand_total: '5.50'
}

// tracking data
const orderTracking =
{
  status: 'placed',
  steps: [
    { status: 'placed', done: true, reached_at: '2026-10-20T18:00:00Z' },
    { status: 'awaiting_delivery', done: false },
    { status: 'assigned_to_trip', done: false },
    { status: 'out_for_delivery', done: false },
    { status: 'delivered', done: false }
  ],
  estimated_arrival: null,
  map: null
}

// return fake data
function fakeBackend(orders)
{
  api.mockImplementation(async (path) =>
  {
    if (path === '/api/orders')
    {
      return { orders: orders }
    }

    if (path === '/api/orders/OFS-TEST001')
    {
      return { order: orderDetails }
    }

    if (path === '/api/orders/OFS-TEST001/tracking')
    {
      return orderTracking
    }
  })
}

// open the page
function openPage(url, user)
{
  render(
    <StoreContext.Provider value={{ user: user, currency: '$' }}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/orders" element={<OrderHistory />} />
          <Route path="/orders/:orderNumber" element={<OrderDetail />} />
          <Route path="/login" element={<p>Sign in page</p>} />
        </Routes>
      </MemoryRouter>
    </StoreContext.Provider>
  )
}

describe('Customer orders', () =>
{
  // clear mocks before test
  beforeEach(() =>
  {
    vi.resetAllMocks()
  })

  //------ Order list test --------
  test('shows the list of orders', async () =>
  {
    fakeBackend([orderInList])
    openPage('/orders', customer)

    expect(await screen.findByText('OFS-TEST001')).toBeInTheDocument()
    expect(screen.getByText('Out for delivery')).toBeInTheDocument()
    expect(screen.getByText('$9.75')).toBeInTheDocument()
  })

  // -------- Order link test -------
  test('clicking an order goes to its own page', async () =>
  {
    fakeBackend([orderInList])
    openPage('/orders', customer)

    const link = await screen.findByRole('link')
    expect(link).toHaveAttribute('href', '/orders/OFS-TEST001')
  })

  // -------- no orders test -------
  test('shows a message when there are no orders', async () =>
  {
    fakeBackend([])
    openPage('/orders', customer)

    expect(
      await screen.findByText('You have not placed any orders yet.')
    ).toBeInTheDocument()
  })

  // -------- error message test -------
  test('shows an error when the backend fails', async () =>
  {
    api.mockRejectedValue(new Error('Could not load orders.'))
    openPage('/orders', customer)

    expect(
      await screen.findByText('Could not load orders.')
    ).toBeInTheDocument()
  })

  // --------- order details test -------
  test('order page shows items, address, card and total', async () =>
  {
    fakeBackend([orderInList])
    openPage('/orders/OFS-TEST001', customer)

    expect(await screen.findByText('2 x Apple')).toBeInTheDocument()
    expect(screen.getByText(/Delivering to 1 Washington Sq/)).toBeInTheDocument()
    expect(screen.getByText('Paid with card ending 4242')).toBeInTheDocument()
    expect(screen.getByText('Free')).toBeInTheDocument()
    expect(screen.getByText('$5.50')).toBeInTheDocument()
  })

  // --------- delivery tracking test -------
  test('order page shows the delivery steps', async () =>
  {
    fakeBackend([orderInList])
    openPage('/orders/OFS-TEST001', customer)

    expect(await screen.findByText('Order placed')).toBeInTheDocument()
    expect(screen.getByText('Delivered')).toBeInTheDocument()
  })

  // --------- user not signed in test -------
  test('sends user to login page when not signed in', async () =>
  {
    openPage('/orders/OFS-TEST001', null)

    expect(await screen.findByText('Sign in page')).toBeInTheDocument()
  })
})