import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Checkout from './Checkout'
import { toCents } from '../components/StripePayment'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import { loadStripe } from '@stripe/stripe-js'

vi.mock('../api', () => ({ api: vi.fn() }))

// Stand-ins for Stripe: the real fields live in Stripe's iframes, so the tests drive these instead.
const stripe = vi.hoisted(() => ({
  submit: vi.fn(),
  createPaymentMethod: vi.fn(),
  walletEvent: { resolve: vi.fn(), paymentFailed: vi.fn(), billingDetails: { name: 'Wallet Name' } },
  elementsOptions: [],
  cardLoadError: null,
}))

vi.mock('@stripe/stripe-js', () => ({ loadStripe: vi.fn(() => Promise.resolve({})) }))

vi.mock('@stripe/react-stripe-js', async () => {
  const { useEffect } = await import('react')
  return {
    Elements: ({ children, options }) => {
      stripe.elementsOptions.push(options)
      return <div>{children}</div>
    },
    CardElement: ({ onLoadError }) => {
      useEffect(() => { if (stripe.cardLoadError) onLoadError({ error: { message: stripe.cardLoadError } }) }, [])
      return <div>Stripe card field</div>
    },
    useStripe: () => ({ createPaymentMethod: stripe.createPaymentMethod }),
    useElements: () => ({ submit: stripe.submit, getElement: () => ({ card: true }) }),
    ExpressCheckoutElement: ({ onClick, onConfirm, onReady }) => {
      useEffect(() => { onReady({ availablePaymentMethods: { googlePay: true } }) }, [])
      return (
        <div>
          <button onClick={() => onClick(stripe.walletEvent)}>Wallet button</button>
          <button onClick={() => onConfirm(stripe.walletEvent)}>Wallet confirm</button>
        </div>
      )
    },
  }
})

const cart = {
  items: [{ product_id: 1, name: 'Apple', quantity: 1, line_total: '2.50' }],
  subtotal: '2.50',
  total_weight_lb: '1.00',
  delivery_fee: '0.00',
  estimated_total: '2.50',
}

const preview = { subtotal: '2.50', total_weight_lb: '1.00', delivery_fee: '0.00', tax: '0.23', grand_total: '2.73' }

// Answers the checkout page's requests; the gateway decides which card form shows.
function mockApi({ gateway = 'stripe', orderError = '' } = {}) {
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/payments/config') return { gateway, currency: 'usd' }
    if (path === '/api/users/me/addresses') {
      return { addresses: [{ address_id: 1, street: '1 Washington Sq', city: 'San Jose', state: 'CA', zip_code: '95192' }] }
    }
    if (path === '/api/checkout/preview') return preview
    if (path === '/api/checkout/estimate') return preview
    if (path === '/api/orders') {
      if (orderError) throw new Error(orderError)
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

// Waits until the page has its totals and PLACE ORDER can be pressed.
async function readyButton() {
  const button = screen.getByRole('button', { name: 'PLACE ORDER' })
  await waitFor(() => expect(button).toBeEnabled())
  return button
}

describe('toCents', () => {
  test('turns money text into whole cents without rounding errors', () => {
    expect(toCents('12.34')).toBe(1234)
    expect(toCents('5')).toBe(500)
    expect(toCents('0.5')).toBe(50)
    expect(toCents('7.05')).toBe(705)
    expect(toCents('20.10')).toBe(2010)
  })
})

describe('checkout with Stripe switched on', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubEnv('VITE_STRIPE_PUBLISHABLE_KEY', 'pk_test_123')
    loadStripe.mockResolvedValue({})
    stripe.submit.mockResolvedValue({})
    stripe.createPaymentMethod.mockResolvedValue({ paymentMethod: { id: 'pm_test_123' } })
    stripe.walletEvent.resolve = vi.fn()
    stripe.walletEvent.paymentFailed = vi.fn()
    stripe.cardLoadError = null
    stripe.elementsOptions = []
    mockApi()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  test('shows Stripe\'s card field instead of the built-in form', async () => {
    renderCheckout()

    expect(await screen.findByText('Stripe card field')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Card number')).not.toBeInTheDocument()
  })

  test('gives Stripe only options the current Stripe.js accepts', async () => {
    renderCheckout()
    await screen.findByText('Stripe card field')

    // Stripe.js refuses the old name "paymentMethodTypes" and then shows no card field at all.
    const walletOptions = stripe.elementsOptions.find((options) => options && options.mode === 'payment')
    expect(walletOptions).toMatchObject({ mode: 'payment', currency: 'usd', paymentMethodCreation: 'manual' })
    expect(walletOptions.amount).toBeGreaterThan(0)
    stripe.elementsOptions.filter(Boolean).forEach((options) => {
      expect(options).not.toHaveProperty('paymentMethodTypes')
    })
  })

  test('uses the card-only field, which cannot show Bank, Klarna or Link tabs', async () => {
    renderCheckout()

    expect(await screen.findByText('Stripe card field')).toBeInTheDocument()
    expect(screen.queryByText(/Klarna|Bank|Link/)).not.toBeInTheDocument()
  })

  test('tells the customer when Stripe cannot load the card form', async () => {
    stripe.cardLoadError = 'Invalid API key.'
    renderCheckout()

    expect(await screen.findByRole('alert')).toHaveTextContent('The card form could not be loaded: Invalid API key.')
  })

  test('sends only the Stripe payment method id to the backend', async () => {
    const user = userEvent.setup()
    renderCheckout()
    await screen.findByText('Stripe card field')

    await user.click(await readyButton())

    expect(await screen.findByText('Order confirmation')).toBeInTheDocument()
    expect(stripe.createPaymentMethod).toHaveBeenCalledWith({
      type: 'card',
      card: { card: true },
      billing_details: { name: 'Anna Rivera', email: 'anna@example.com' },
    })
    expect(api).toHaveBeenCalledWith('/api/orders', {
      method: 'POST',
      body: { address_id: 1, payment_token: 'pm_test_123', idempotency_key: expect.any(String) },
    })
  })

  test('shows Stripe\'s message and sends no order when the card is incomplete', async () => {
    stripe.createPaymentMethod.mockResolvedValue({ error: { message: 'Your card number is incomplete.' } })
    const user = userEvent.setup()
    renderCheckout()
    await screen.findByText('Stripe card field')

    await user.click(await readyButton())

    expect(await screen.findByRole('alert')).toHaveTextContent('Your card number is incomplete.')
    expect(api.mock.calls.some(([path]) => path === '/api/orders')).toBe(false)
  })

  test('a declined payment shows the backend message and keeps the page', async () => {
    mockApi({ orderError: 'Payment declined: Card declined. Your cart has not changed.' })
    const user = userEvent.setup()
    renderCheckout()
    await screen.findByText('Stripe card field')

    await user.click(await readyButton())

    expect(await screen.findByRole('alert')).toHaveTextContent('Payment declined')
    expect(screen.getByRole('button', { name: 'PLACE ORDER' })).toBeEnabled()
  })

  test('a wallet button places the order with the wallet\'s payment method', async () => {
    const user = userEvent.setup()
    renderCheckout()
    await screen.findByText('Stripe card field')
    await readyButton()

    await user.click(screen.getByRole('button', { name: 'Wallet button' }))
    expect(stripe.walletEvent.resolve).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Wallet confirm' }))

    expect(await screen.findByText('Order confirmation')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/orders', expect.objectContaining({
      body: expect.objectContaining({ payment_token: 'pm_test_123' }),
    }))
    expect(stripe.walletEvent.paymentFailed).not.toHaveBeenCalled()
  })

  test('a wallet payment the backend refuses closes the wallet sheet as failed', async () => {
    mockApi({ orderError: 'Payment declined: Card declined.' })
    const user = userEvent.setup()
    renderCheckout()
    await screen.findByText('Stripe card field')
    await readyButton()

    await user.click(screen.getByRole('button', { name: 'Wallet confirm' }))

    await waitFor(() => expect(stripe.walletEvent.paymentFailed).toHaveBeenCalledWith({ reason: 'fail' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment declined')
  })

  test('the wallet sheet stays closed until a guest has filled in their details', async () => {
    const user = userEvent.setup()
    renderCheckout({ user: null, guestCheckout: vi.fn() })
    await screen.findByText('Stripe card field')

    await user.click(screen.getByRole('button', { name: 'Wallet button' }))

    expect(stripe.walletEvent.resolve).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your first and last name.')
  })

  test('uses the built-in form when the backend gateway is the fake one', async () => {
    mockApi({ gateway: 'fake' })

    renderCheckout()

    expect(await screen.findByPlaceholderText('Card number')).toBeInTheDocument()
    expect(screen.queryByText('Stripe card field')).not.toBeInTheDocument()
  })
})
