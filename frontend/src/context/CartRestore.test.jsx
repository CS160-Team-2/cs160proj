import React, { useContext } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StoreContextProvider, { StoreContext } from './StoreContext'

vi.mock('../api', () => ({ api: vi.fn() }))

import { api } from '../api'

const savedCart = {
  items: [{ product_id: 1, name: 'Apple', quantity: 2, line_total: '5.00', image_key: 'apple' }],
  item_count: 2,
  subtotal: '5.00',
  total_weight_lb: '2.00',
  delivery_fee: '0.00',
  estimated_total: '5.00',
  can_check_out: true,
}

// Shows the cart count the header would show.
const CartCount = () => {
  const { getShoppingCartCount } = useContext(StoreContext)
  return <p data-testid="count">{getShoppingCartCount()}</p>
}

// Answers the page-load requests the way the backend does for a returning visitor.
function mockBackend({ cart = savedCart, cartFails = false } = {}) {
  api.mockImplementation(async (path) => {
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') {
      if (cartFails) throw new Error('offline')
      return { cart }
    }
    throw new Error('not signed in')
  })
}

describe('cart restored on page load', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  test('a returning visitor sees the saved cart count straight away', async () => {
    mockBackend()

    render(<StoreContextProvider><CartCount /></StoreContextProvider>)

    expect(await screen.findByText('2')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/cart')
  })

  test('refreshing the page asks the backend for the cart again', async () => {
    mockBackend()
    const first = render(<StoreContextProvider><CartCount /></StoreContextProvider>)
    await screen.findByText('2')
    first.unmount()

    render(<StoreContextProvider><CartCount /></StoreContextProvider>)

    expect(await screen.findByText('2')).toBeInTheDocument()
    expect(api.mock.calls.filter(([path]) => path === '/api/cart')).toHaveLength(2)
  })

  test('an expired cart starts empty without an error', async () => {
    mockBackend({ cart: { ...savedCart, items: [], item_count: 0, can_check_out: false } })

    render(<StoreContextProvider><CartCount /></StoreContextProvider>)

    expect(await screen.findByTestId('count')).toHaveTextContent('0')
  })

  test('the count stays at zero when the cart cannot be loaded', async () => {
    mockBackend({ cartFails: true })

    render(<StoreContextProvider><CartCount /></StoreContextProvider>)

    expect(await screen.findByTestId('count')).toHaveTextContent('0')
  })
})
