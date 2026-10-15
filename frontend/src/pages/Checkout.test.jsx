import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Checkout from './Checkout'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'

vi.mock('../api', () => ({ api: vi.fn() }))

const address = {
  address_id: 1,
  street: '1 Washington Sq',
  city: 'San Jose',
  state: 'CA',
  zip_code: '95192',
}

const cart = {
  items: [{
    product_id: 1,
    name: 'Apple',
    quantity: 1,
    line_total: '2.50',
  }],
  subtotal: '2.50',
  total_weight_lb: '1.00',
  delivery_fee: '0.00',
}

const preview = {
  subtotal: '2.50',
  total_weight_lb: '1.00',
  delivery_fee: '0.00',
  tax: '0.25',
  grand_total: '2.75',
}

function mockApi({
  previewError = '',
  addressError = '',
  pendingPreview = false,
} = {}) {
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/users/me/addresses') {
      if (options.method === 'POST') {
        if (addressError) throw new Error(addressError)
        return { address: { ...options.body, address_id: 2 } }
      }
      return { addresses: [address] }
    }

    if (path === '/api/checkout/preview') {
      if (pendingPreview) return new Promise(() => {})
      if (previewError) throw new Error(previewError)
      return preview
    }

    if (path === '/api/orders') {
      if (options.body.payment_token === 'tok_declined') {
        throw new Error('Card declined')
      }
      return { order: { order_number: 'OFS-TEST001' } }
    }

    throw new Error(`Unexpected API request: ${path}`)
  })
}

function renderCheckout(overrides = {}) {
  const context = {
    user: { user_id: 1, role: 'customer' },
    currency: '$',
    cart,
    reloadCart: vi.fn().mockResolvedValue(undefined),
    reloadProducts: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }

  render(
    <StoreContext.Provider value={context}>
      <MemoryRouter initialEntries={['/checkout']}>
        <Routes>
          <Route path="/checkout" element={<Checkout />} />
          <Route
            path="/login"
            element={<p>Sign in to continue</p>}
          />
          <Route
            path="/orders"
            element={<p>Order confirmation</p>}
          />
        </Routes>
      </MemoryRouter>
    </StoreContext.Provider>
  )

  return context
}

async function readyButton() {
  const button = screen.getByRole('button', {
    name: 'PLACE ORDER',
  })

  await waitFor(() => expect(button).toBeEnabled())
  return button
}

async function fillCard(user, number = '4242 4242 4242 4242') 
{
  await user.type(screen.getByPlaceholderText('Name on card'), 'Anna Rivera')
  await user.type(screen.getByPlaceholderText('Card number'), number)
  await user.type(screen.getByPlaceholderText('MM/YY'), '12/30')
  await user.type(screen.getByPlaceholderText('CVC'), '123')
}

describe('Checkout', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('redirects signed-out visitors to sign in', async () => {
    renderCheckout({ user: null })

    expect(
      await screen.findByText('Sign in to continue')
    ).toBeInTheDocument()

    expect(api).not.toHaveBeenCalled()
  })

  test('staff accounts cannot place orders', () => {
    renderCheckout({ user: { role: 'employee' } })

    expect(
      screen.getByText('Staff accounts cannot place orders.')
    ).toBeInTheDocument()

    expect(
      screen.queryByRole('button', { name: 'PLACE ORDER' })
    ).not.toBeInTheDocument()

    expect(api).not.toHaveBeenCalled()
  })

  test('an empty cart shows a shopping link instead of checkout', async () => {
    renderCheckout({ cart: { ...cart, items: [] } })

    await waitFor(() => {
      expect(api).toHaveBeenCalledWith('/api/users/me/addresses')
    })

    expect(
      screen.getByText('Your cart is empty.')
    ).toBeInTheDocument()

    expect(
      screen.getByRole('link', { name: 'CONTINUE SHOPPING' })
    ).toHaveAttribute('href', '/products')

    expect(
      screen.queryByRole('button', { name: 'PLACE ORDER' })
    ).not.toBeInTheDocument()
  })

  test('shows the saved address and backend order breakdown', async () => {
    renderCheckout()
    await readyButton()

    expect(screen.getByRole('radio')).toBeChecked()

    expect(
      screen.getByText('1 Washington Sq, San Jose, CA 95192')
    ).toBeInTheDocument()

    expect(screen.getByText('1 x Apple')).toBeInTheDocument()
    expect(screen.getByText('1.00 lb')).toBeInTheDocument()
    expect(screen.getByText('Free')).toBeInTheDocument()
    expect(screen.getByText('$0.25')).toBeInTheDocument()
    expect(screen.getByText('$2.75')).toBeInTheDocument()
  })

  test('cannot place an order while the preview is loading', async () => {
    mockApi({ pendingPreview: true })
    const user = userEvent.setup()
    renderCheckout()

    await screen.findByRole('radio')

    const button = screen.getByRole('button', {
      name: 'PLACE ORDER',
    })

    expect(button).toBeDisabled()
    await user.click(button)

    expect(
      api.mock.calls.some(([path]) => path === '/api/orders')
    ).toBe(false)
  })

  test('shows preview errors and prevents order submission', async () => {
    mockApi({ previewError: 'Apple is out of stock.' })
    renderCheckout()

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('Apple is out of stock.')

    expect(
      screen.getByRole('link', { name: 'Review your cart' })
    ).toHaveAttribute('href', '/cart')

    expect(
      screen.getByRole('button', { name: 'PLACE ORDER' })
    ).toBeDisabled()
  })

  test.each([false, true])(
    'saving a new address handles rejection=%s',
    async (rejected) => {
      mockApi({
        addressError: rejected ? 'Address not found.' : '',
      })

      const user = userEvent.setup()
      renderCheckout()
      await readyButton()

      await user.click(
        screen.getByRole('button', { name: '+ Add a new address' })
      )

      await user.type(
        screen.getByPlaceholderText('Street address'),
        '123 Main St'
      )

      await user.type(
        screen.getByPlaceholderText('City'),
        'San Jose'
      )

      await user.type(
        screen.getByPlaceholderText('ZIP'),
        '95112'
      )

      await user.click(
        screen.getByRole('button', { name: 'Save address' })
      )

      expect(api).toHaveBeenCalledWith('/api/users/me/addresses', {
        method: 'POST',
        body: {
          street: '123 Main St',
          city: 'San Jose',
          state: 'CA',
          zip_code: '95112',
        },
      })

      if (rejected) {
        expect(
          await screen.findByRole('alert')
        ).toHaveTextContent('Address not found.')

        expect(
          screen.getByPlaceholderText('Street address')
        ).toHaveValue('123 Main St')
      } else {
        expect(
          await screen.findByText('123 Main St, San Jose, CA 95112')
        ).toBeInTheDocument()

        expect(screen.getAllByRole('radio')[1]).toBeChecked()

        expect(
          screen.queryByPlaceholderText('Street address')
        ).not.toBeInTheDocument()
      }
    }
  )

  test('successful checkout refreshes data and opens the order confirmation', async () => {
    const user = userEvent.setup()
    const context = renderCheckout()
    await readyButton()

    await fillCard(user)
    await user.click(await readyButton())

    expect(
      await screen.findByText('Order confirmation')
    ).toBeInTheDocument()

    expect(context.reloadCart).toHaveBeenCalledTimes(1)
    expect(context.reloadProducts).toHaveBeenCalledTimes(1)

    expect(api).toHaveBeenCalledWith('/api/orders', {
      method: 'POST',
      body: {
        address_id: 1,
        payment_token: 'tok_visa',
        idempotency_key: expect.any(String),
      },
    })
  })

  test('a declined payment allows retry using the same checkout key', async () => {
    const user = userEvent.setup()
    const context = renderCheckout()
    await readyButton()

    // declined test card
    await fillCard(user, '4000 0000 0000 0002')
    await user.click(await readyButton())

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('Card declined')

    expect(context.reloadCart).not.toHaveBeenCalled()
    expect(context.reloadProducts).not.toHaveBeenCalled()
    expect(screen.getByText('1 x Apple')).toBeInTheDocument()

    // retry with an approved card; name, expiry and CVC stay filled in
    const cardNumber = screen.getByPlaceholderText('Card number')
    await user.clear(cardNumber)
    await user.type(cardNumber, '4242 4242 4242 4242')
    await user.click(await readyButton())

    expect(
      await screen.findByText('Order confirmation')
    ).toBeInTheDocument()

    const orders = api.mock.calls.filter(
      ([path]) => path === '/api/orders'
    )

    expect(orders).toHaveLength(2)
    expect(orders[0][1].body.payment_token).toBe('tok_declined')
    expect(orders[1][1].body.payment_token).toBe('tok_visa')
    // same checkout key on retry, so the backend can never charge twice
    expect(orders[1][1].body.idempotency_key).toBe(orders[0][1].body.idempotency_key)
  })
})