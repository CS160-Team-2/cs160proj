import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Cart from '../../src/pages/Cart'
import { api } from '../../src/api'
import { renderWithProviders } from '../renderWithProviders'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

const product = {
  product_id: 1,
  name: 'Apple',
  price: '2.50',
  unit_weight_lb: '1.00',
  stock: 5,
  available: true,
  image_key: 'apple',
}

const emptyCart = {
  items: [],
  item_count: 0,
  subtotal: '0.00',
  total_weight_lb: '0.00',
  delivery_fee: '0.00',
  estimated_total: '0.00',
  can_check_out: false,
}

const filledCart = {
  items: [{ ...product, quantity: 2, line_total: '5.00' }],
  item_count: 2,
  subtotal: '5.00',
  total_weight_lb: '2.00',
  delivery_fee: '0.00',
  estimated_total: '5.00',
  can_check_out: true,
}

function mockApi(cart = filledCart) {
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/products') {
      return { products: [product] }
    }

    if (path === '/api/auth/me') {
      return { user: null }
    }

    if (path === '/api/cart') {
      return { cart }
    }

    if (path === '/api/cart/items/1' && options.method === 'PATCH') {
      return {
        cart: {
          ...filledCart,
          items: [{ ...product, quantity: 3, line_total: '7.50' }],
          item_count: 3,
          subtotal: '7.50',
          total_weight_lb: '3.00',
          estimated_total: '7.50',
        },
      }
    }

    if (path === '/api/cart/items/1' && options.method === 'DELETE') {
      return { cart: emptyCart }
    }

    throw new Error(
      `Unexpected API request: ${options.method || 'GET'} ${path}`
    )
  })
}

async function openFilledCart() {
  renderWithProviders(<Cart />, { route: '/cart' })
  await screen.findByRole('spinbutton')
}

describe('Cart', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('shows an empty cart and a shopping link', async () => {
    mockApi(emptyCart)
    renderWithProviders(<Cart />, { route: '/cart' })

    await waitFor(() => {
      expect(api).toHaveBeenCalledWith('/api/cart')
    })

    expect(screen.getByText('Your cart is empty.')).toBeInTheDocument()

    expect(
      screen.getByRole('link', { name: 'CONTINUE SHOPPING' })
    ).toHaveAttribute('href', '/')

    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  test('shows products, quantities, totals, and the checkout link', async () => {
    await openFilledCart()

    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.getByText('$2.50')).toBeInTheDocument()
    expect(screen.getByText('1.00 lb')).toBeInTheDocument()
    expect(screen.getByRole('spinbutton')).toHaveValue(2)

    // Subtotal and total each display $5.00.
    expect(screen.getAllByText('$5.00')).toHaveLength(2)

    expect(screen.getByText('2.00 lb')).toBeInTheDocument()
    expect(screen.getByText('Free')).toBeInTheDocument()

    expect(
      screen.getByRole('link', { name: 'PROCEED TO CHECKOUT' })
    ).toHaveAttribute('href', '/checkout')
  })

  // The store cannot be reached: the cart page must not claim the cart is empty.
  test('says it could not load the cart, and TRY AGAIN loads it', async () => {
    const user = userEvent.setup()
    let down = true
    api.mockImplementation(async (path) => {
      if (path === '/api/products') return { products: [product] }
      if (path === '/api/auth/me') return { user: null }
      if (path === '/api/cart') {
        if (down) throw Object.assign(new Error('We cannot reach the store right now. Check your internet connection and try again.'), { status: 0, code: 'NETWORK' })
        return { cart: filledCart }
      }
      throw new Error(`Unexpected ${path}`)
    })
    renderWithProviders(<Cart />, { route: '/cart' })

    expect(await screen.findByRole('heading', { name: 'We could not load your cart' })).toBeInTheDocument()
    expect(screen.getByText(/cannot reach the store/)).toBeInTheDocument()
    expect(screen.queryByText('Your cart is empty.')).not.toBeInTheDocument()

    down = false
    await user.click(screen.getByRole('button', { name: 'TRY AGAIN' }))

    expect(await screen.findByText('Apple')).toBeInTheDocument()
    expect(screen.queryByText('We could not load your cart')).not.toBeInTheDocument()
  })

  test('a server error on the cart also says so, but a staff account with no cart still gets the empty page', async () => {
    api.mockImplementation(async (path) => {
      if (path === '/api/products') return { products: [product] }
      if (path === '/api/auth/me') return { user: null }
      if (path === '/api/cart') throw Object.assign(new Error('Staff accounts have no cart'), { status: 403, code: 'FORBIDDEN' })
      throw new Error(`Unexpected ${path}`)
    })
    renderWithProviders(<Cart />, { route: '/cart' })

    expect(await screen.findByText('Your cart is empty.')).toBeInTheDocument()
  })

  // C8: the cart explains the delivery charge and how close the order is to the line.
  test('says delivery is free and how far the order is from the $10 charge', async () => {
    mockApi({ ...filledCart, total_weight_lb: '16.50', free_delivery_below_lb: '20.00', delivery_charge: '10.00' })
    renderWithProviders(<Cart />, { route: '/cart' })

    expect(await screen.findByTestId('delivery-hint')).toHaveTextContent('Delivery is free because your order is under 20 lb. At 20 lb or more it costs $10.00, so 3.50 lb more would add the charge.')
  })

  test('says why delivery costs $10 and how much to take out to make it free', async () => {
    mockApi({ ...filledCart, total_weight_lb: '22.00', delivery_fee: '10.00', estimated_total: '15.00', free_delivery_below_lb: '20.00', delivery_charge: '10.00' })
    renderWithProviders(<Cart />, { route: '/cart' })

    expect(await screen.findByTestId('delivery-hint')).toHaveTextContent('Delivery costs $10.00 because your order is 20 lb or more. Take out 2.01 lb or more and delivery is free.')
    expect(screen.getByText('$10.00', { selector: 'p' })).toBeInTheDocument()
  })

  test('changing quantity displays the updated quantity and totals', async () => {
    await openFilledCart()

    fireEvent.change(screen.getByRole('spinbutton'), {
      target: { value: '3' },
    })

    await waitFor(() => {
      expect(screen.getByRole('spinbutton')).toHaveValue(3)
    })

    expect(screen.getAllByText('$7.50')).toHaveLength(2)
    expect(screen.getByText('3.00 lb')).toBeInTheDocument()

    expect(api).toHaveBeenCalledWith('/api/cart/items/1', {
      method: 'PATCH',
      body: { quantity: 3 },
    })
  })

  test('removing the final item displays the empty cart', async () => {
    const user = userEvent.setup()
    await openFilledCart()

    await user.click(
      screen.getByRole('button', { name: 'Remove Apple' })
    )

    expect(
      await screen.findByText('Your cart is empty.')
    ).toBeInTheDocument()

    expect(screen.queryByText('Apple')).not.toBeInTheDocument()

    expect(
      screen.queryByRole('link', { name: 'PROCEED TO CHECKOUT' })
    ).not.toBeInTheDocument()
  })

  test('shows a rejected quantity message and keeps the previous quantity', async () => {
    await openFilledCart()

    api.mockRejectedValueOnce(new Error('Only 5 available.'))

    fireEvent.change(screen.getByRole('spinbutton'), {
      target: { value: '6' },
    })

    expect(
      await screen.findByText('Only 5 available.')
    ).toBeInTheDocument()

    expect(screen.getByRole('spinbutton')).toHaveValue(2)
  })

  test('blocks checkout and explains an unavailable item', async () => {
    mockApi({
      ...filledCart,
      items: [{
        ...filledCart.items[0],
        problem: 'Only 1 available.',
      }],
      can_check_out: false,
    })

    await openFilledCart()

    expect(screen.getByText('Only 1 available.')).toBeInTheDocument()

    expect(
      screen.getByText(
        'Please fix the items marked above before checking out.'
      )
    ).toBeInTheDocument()

    expect(
      screen.queryByRole('link', { name: 'PROCEED TO CHECKOUT' })
    ).not.toBeInTheDocument()
  })
})