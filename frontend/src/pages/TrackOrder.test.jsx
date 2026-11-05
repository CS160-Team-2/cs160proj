// test track order page
// guest user
// findByText() - wait for text to show up
// getByText() - check if text is there
// user.type() - type in a box
// user.click() - click a button

import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import TrackOrder from './TrackOrder'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'

// Use fake data for testing
vi.mock('../api', () => ({ api: vi.fn() }))

// Order details
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

// open as a guest
function openPage()
{
  render(
    <StoreContext.Provider value={{ user: null, currency: '$' }}>
      <MemoryRouter>
        <TrackOrder />
      </MemoryRouter>
    </StoreContext.Provider>
  )
}

async function lookUp(user, orderNumber, email)
{
  await user.type(screen.getByPlaceholderText('Order number, like OFS-AB12CD'), orderNumber)
  await user.type(screen.getByPlaceholderText('Email'), email)
  await user.click(screen.getByRole('button', { name: 'Track order' }))
}

describe('Track order (guest)', () =>
{
  // clear mocks before each test
  beforeEach(() =>
  {
    vi.resetAllMocks()
  })

  // ------- form test -------
  test('shows the order number box, email box and button', () =>
  {
    openPage()

    expect(screen.getByPlaceholderText('Order number, like OFS-AB12CD')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Track order' })).toBeInTheDocument()
  })

  // --------- correct order number and email test -------
  test('shows the order when the number and email match', async () =>
  {
    api.mockResolvedValue({ order: orderDetails, tracking: orderTracking })
    const user = userEvent.setup()
    openPage()

    await lookUp(user, 'OFS-TEST001', 'anna@example.com')

    expect(await screen.findByText('2 x Apple')).toBeInTheDocument()
    expect(screen.getByText('Order placed')).toBeInTheDocument()
    expect(screen.getByText('$5.50')).toBeInTheDocument()
  })

  // --------- check data sent to api test -------
  test('sends the order number in capitals and removes email spaces', async () =>
  {
    api.mockResolvedValue({ order: orderDetails, tracking: orderTracking })
    const user = userEvent.setup()
    openPage()

    await lookUp(user, 'ofs-test001', '  anna@example.com  ')

    expect(api).toHaveBeenCalledWith('/api/orders/lookup',
    {
      method: 'POST',
      body:
      {
        order_number: 'OFS-TEST001',
        email: 'anna@example.com'
      }
    })
  })

  // --------- wrong order number or email test -------
  test('shows an error when the order is not found', async () =>
  {
    api.mockRejectedValue(new Error('We could not find an order with that number and email.'))
    const user = userEvent.setup()
    openPage()

    await lookUp(user, 'OFS-WRONG1', 'anna@example.com')

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not find an order')
    expect(screen.queryByText('2 x Apple')).not.toBeInTheDocument()
  })

  // --------- empty boxes test -------
  test('does not search when the boxes are empty', async () =>
  {
    const user = userEvent.setup()
    openPage()

    await user.click(screen.getByRole('button', { name: 'Track order' }))

    expect(api).not.toHaveBeenCalled()
  })

  // --------- sign in link test -------
  test('has a sign in link for customers', () =>
  {
    openPage()

    expect(screen.getByRole('link', { name: 'Sign in' }))
      .toHaveAttribute('href', '/login?next=/orders')
  })
})