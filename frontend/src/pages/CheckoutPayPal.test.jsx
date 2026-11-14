import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Checkout from './Checkout'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'

vi.mock('../api', () => ({ api: vi.fn() }))

// Stand-ins for PayPal's buttons: the real ones live in PayPal's own frames.
const paypal = vi.hoisted(() => ({
  scriptOptions: null,
  buttonProps: null,
  actions: { resolve: vi.fn(), reject: vi.fn() },
  errorToShow: null,
}))

vi.mock('@paypal/react-paypal-js', () => ({
  PayPalScriptProvider: ({ children, options }) => {
    paypal.scriptOptions = options
    return <div>{children}</div>
  },
  PayPalButtons: ({ onClick, createOrder, onApprove, onCancel, fundingSource }) => {
    paypal.buttonProps = { fundingSource }
    return (
    <div>
      <button onClick={() => onClick({}, paypal.actions)}>Start PayPal</button>
      <button onClick={async () => onApprove({ orderID: await createOrder() })}>Approve in PayPal</button>
      <button onClick={() => onCancel()}>Cancel in PayPal</button>
    </div>
    )
  },
}))

const cart = {
  items: [{ product_id: 1, name: 'Apple', quantity: 1, line_total: '2.50' }],
  subtotal: '2.50',
  total_weight_lb: '1.00',
  delivery_fee: '0.00',
  estimated_total: '2.50',
}

const preview = { subtotal: '2.50', total_weight_lb: '1.00', delivery_fee: '0.00', tax: '0.23', grand_total: '2.73' }

// Answers the checkout page's requests; PayPal is on unless told otherwise, and orderError (text or an Error) makes placing the order fail.
function mockApi({ paypalOn = true, orderError = '' } = {}) {
  api.mockImplementation(async (path) => {
    if (path === '/api/payments/config') {
      return { gateway: 'fake', currency: 'usd', paypal: { enabled: paypalOn, client_id: paypalOn ? 'client-123' : '', currency: 'USD' } }
    }
    if (path === '/api/users/me/addresses') {
      return { addresses: [{ address_id: 1, street: '1 Washington Sq', city: 'San Jose', state: 'CA', zip_code: '95192' }] }
    }
    if (path === '/api/checkout/preview' || path === '/api/checkout/estimate') return preview
    if (path === '/api/payments/paypal/order') return { id: 'ORDER123' }
    if (path === '/api/orders') {
      if (orderError) throw orderError instanceof Error ? orderError : new Error(orderError)
      return { order: { order_number: 'OFS-TEST001' } }
    }
    throw new Error(`Unexpected API request: ${path}`)
  })
}

// Draws the checkout page for a signed-in customer unless another user is given.
function renderCheckout(overrides = {}) {
  const context = {
    user: { user_id: 1, role: 'customer', full_name: 'Anna Rivera', email: 'anna@example.com' },
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
          <Route path="/orders" element={<p>Order confirmation</p>} />
        </Routes>
      </MemoryRouter>
    </StoreContext.Provider>,
  )
  return context
}

describe('choosing how to pay', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    paypal.scriptOptions = null
    paypal.buttonProps = null
    paypal.actions = { resolve: vi.fn(), reject: vi.fn() }
    mockApi()
  })

  test('offers card and PayPal as radio buttons, with card chosen first', async () => {
    renderCheckout()

    const card = await screen.findByRole('radio', { name: /Credit or debit card/ })
    expect(card).toBeChecked()
    expect(screen.getByRole('radio', { name: /PayPal/ })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'PLACE ORDER' })).toBeInTheDocument()
  })

  test('shows no choice when PayPal is not set up', async () => {
    mockApi({ paypalOn: false })
    renderCheckout()

    expect(await screen.findByPlaceholderText('Card number')).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /PayPal/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /Credit or debit card/ })).not.toBeInTheDocument()
  })

  test('choosing PayPal swaps the card form and the Place Order button for PayPal\'s buttons', async () => {
    const user = userEvent.setup()
    renderCheckout()

    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))

    expect(screen.getByRole('button', { name: 'Start PayPal' })).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Card number')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'PLACE ORDER' })).not.toBeInTheDocument()
    expect(paypal.scriptOptions).toMatchObject({ clientId: 'client-123', currency: 'USD', intent: 'capture' })
    expect(paypal.scriptOptions).not.toHaveProperty('enable-funding')
    expect(paypal.scriptOptions['disable-funding']).toBe('card,credit,paylater,venmo')
    expect(paypal.buttonProps).toEqual({ fundingSource: 'paypal' })
  })

  test('going back to card brings the card form and Place Order back', async () => {
    const user = userEvent.setup()
    renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))

    await user.click(screen.getByRole('radio', { name: /Credit or debit card/ }))

    expect(screen.getByPlaceholderText('Card number')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'PLACE ORDER' })).toBeInTheDocument()
  })

  test('an approved PayPal payment places the order with the PayPal order id', async () => {
    const user = userEvent.setup()
    const context = renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))
    await screen.findByText('1 Washington Sq, San Jose, CA 95192')

    await user.click(screen.getByRole('button', { name: 'Approve in PayPal' }))

    expect(await screen.findByText('Order confirmation')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/payments/paypal/order', { method: 'POST' })
    expect(api).toHaveBeenCalledWith('/api/orders', {
      method: 'POST',
      body: { address_id: 1, payment_token: 'paypal:ORDER123', idempotency_key: expect.any(String) },
    })
    expect(context.reloadCart).toHaveBeenCalled()
  })

  test('a payment the server refuses shows its message and keeps the page', async () => {
    mockApi({ orderError: 'Payment declined: PayPal could not take the payment. Your cart has not changed.' })
    const user = userEvent.setup()
    renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))
    await screen.findByText('1 Washington Sq, San Jose, CA 95192')

    await user.click(screen.getByRole('button', { name: 'Approve in PayPal' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Payment declined')
    expect(screen.getByRole('button', { name: 'Start PayPal' })).toBeInTheDocument()
  })

  test('a cart that changed since it was filled links back to the cart', async () => {
    mockApi({ orderError: Object.assign(new Error('Some items in your cart changed.'), { code: 'CART_NEEDS_CHANGES' }) })
    const user = userEvent.setup()
    renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))
    await screen.findByText('1 Washington Sq, San Jose, CA 95192')

    await user.click(screen.getByRole('button', { name: 'Approve in PayPal' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Some items in your cart changed.')
    expect(screen.getByRole('link', { name: 'Review your cart' })).toHaveAttribute('href', '/cart')
  })

  test('a guest cannot start PayPal until their details are filled in', async () => {
    const user = userEvent.setup()
    renderCheckout({ user: null, guestCheckout: vi.fn() })
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))

    await user.click(screen.getByRole('button', { name: 'Start PayPal' }))

    expect(paypal.actions.reject).toHaveBeenCalled()
    expect(paypal.actions.resolve).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your first and last name.')
  })

  test('a signed-in customer with an address can start PayPal', async () => {
    const user = userEvent.setup()
    renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/users/me/addresses'))
    await screen.findByText('1 Washington Sq, San Jose, CA 95192')

    await user.click(screen.getByRole('button', { name: 'Start PayPal' }))

    expect(paypal.actions.resolve).toHaveBeenCalled()
    expect(paypal.actions.reject).not.toHaveBeenCalled()
  })

  test('cancelling at PayPal says the cart has not changed', async () => {
    const user = userEvent.setup()
    renderCheckout()
    await user.click(await screen.findByRole('radio', { name: /PayPal/ }))

    await user.click(screen.getByRole('button', { name: 'Cancel in PayPal' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Your cart has not changed.')
  })
})
