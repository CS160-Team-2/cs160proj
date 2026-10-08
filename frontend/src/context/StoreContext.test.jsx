import React, { useContext } from 'react'
import { describe, expect, test, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { StoreContext } from './StoreContext'
import StoreContextProvider from './StoreContext'

vi.mock('../api', () =>
({
  api: vi.fn(),
}))

import { api } from '../api'

const products =
[
  {
    product_id: 1,
    name: 'Apple',
    price: '2.50',
    unit_weight_lb: '1.00',
    stock: 5,
    available: true,
    image_key: 'apple',
  },
]

const emptyCart =
{
  items: [],
  item_count: 0,
  subtotal: '0.00',
  total_weight_lb: '0.00',
  delivery_fee: '0.00',
  estimated_total: '0.00',
  can_check_out: false,
}

const TestComponent = () =>
{
  const {
    cart,
    shoppingCartItems,
    addToCart,
    products,
    productsLoading,
  } = useContext(StoreContext)

  return (
    <>
      <p data-testid="cart-count">{cart.item_count}</p>
      <p data-testid="products-loaded">
        {productsLoading ? 'loading' : products.length}
      </p>
      <p data-testid="cart-item-1">
        {shoppingCartItems[1] || 0}
      </p>

      <button onClick={() => addToCart(1, 1)}>
        Add Apple
      </button>

      <button onClick={() => addToCart(1, 10)}>
        Add Too Much
      </button>

      <button onClick={() => addToCart(999, 1)}>
        Add Invalid
      </button>
    </>
  )
}

const renderStoreContext = () =>
{
  return render(
    <StoreContextProvider>
      <TestComponent />
    </StoreContextProvider>
  )
}

describe('StoreContext', () =>
{
  beforeEach(() =>
  {
    vi.clearAllMocks()

    api.mockImplementation(async (path) =>
    {
      if (path === '/api/products')
      {
        return { products }
      }

      if (path === '/api/cart')
      {
        return { cart: emptyCart }
      }

      if (path === '/api/auth/me')
      {
        return { user: null }
      }

      return { cart: emptyCart }
    })
  })

  test('cart starts with 0 items', async () =>
  {
    renderStoreContext()

    expect(screen.getByTestId('cart-count')).toHaveTextContent('0')

    await waitFor(() =>
    {
      expect(screen.getByTestId('products-loaded')).toHaveTextContent('1')
    })
  })

  test('can add an item to the cart', async () =>
  {
    api.mockImplementation(async (path) =>
    {
      if (path === '/api/products')
      {
        return { products }
      }

      if (path === '/api/cart')
      {
        return { cart: emptyCart }
      }

      if (path === '/api/auth/me')
      {
        return { user: null }
      }

      if (path === '/api/cart/items')
      {
        return {
          cart: {
            ...emptyCart,
            items: [{ product_id: 1, quantity: 1 }],
            item_count: 1,
          },
        }
      }

      return { cart: emptyCart }
    })

    renderStoreContext()

    await waitFor(() =>
    {
      expect(screen.getByTestId('products-loaded')).toHaveTextContent('1')
    })

    await act(async () =>
    {
      screen.getByRole('button', { name: 'Add Apple' }).click()
    })

    await waitFor(() =>
    {
      expect(screen.getByTestId('cart-count')).toHaveTextContent('1')
    })
  })

  test('does not add more than available stock', async () =>
  {
    api.mockImplementation(async (path, options = {}) =>
    {
      if (path === '/api/products')
      {
        return { products }
      }

      if (path === '/api/cart')
      {
        return { cart: emptyCart }
      }

      if (path === '/api/auth/me')
      {
        return { user: null }
      }

      if (path === '/api/cart/items')
      {
        if (options.body?.quantity > 5)
        {
          throw new Error('Only 5 more available.')
        }

        return {
          cart: {
            ...emptyCart,
            items: [
              {
                product_id: 1,
                quantity: options.body?.quantity || 0,
              },
            ],
            item_count: options.body?.quantity || 0,
          },
        }
      }

      return { cart: emptyCart }
    })

    renderStoreContext()

    await waitFor(() =>
    {
      expect(screen.getByTestId('products-loaded')).toHaveTextContent('1')
    })

    await act(async () =>
    {
      screen.getByRole('button', { name: 'Add Too Much' }).click()
    })

    expect(screen.getByTestId('cart-count')).toHaveTextContent('0')
  })

  test('does not add an item when stock is 0', async () =>
  {
    const outOfStockProducts =
    [
      {
        ...products[0],
        stock: 0,
        available: false,
      },
    ]

    api.mockImplementation(async (path) =>
    {
      if (path === '/api/products')
      {
        return { products: outOfStockProducts }
      }

      if (path === '/api/cart')
      {
        return { cart: emptyCart }
      }

      if (path === '/api/auth/me')
      {
        return { user: null }
      }

      if (path === '/api/cart/items')
      {
        throw new Error('Out of stock')
      }

      return { cart: emptyCart }
    })

    renderStoreContext()

    await waitFor(() =>
    {
      expect(screen.getByTestId('products-loaded')).toHaveTextContent('1')
    })

    await act(async () =>
    {
      screen.getByRole('button', { name: 'Add Apple' }).click()
    })

    expect(screen.getByTestId('cart-count')).toHaveTextContent('0')
  })

  test('does not add an invalid product id', async () =>
  {
    api.mockImplementation(async (path) =>
    {
      if (path === '/api/products')
      {
        return { products }
      }

      if (path === '/api/cart')
      {
        return { cart: emptyCart }
      }

      if (path === '/api/auth/me')
      {
        return { user: null }
      }

      if (path === '/api/cart/items')
      {
        throw new Error('Product not found')
      }

      return { cart: emptyCart }
    })

    renderStoreContext()

    await waitFor(() =>
    {
      expect(screen.getByTestId('products-loaded')).toHaveTextContent('1')
    })

    await act(async () =>
    {
      screen.getByRole('button', { name: 'Add Invalid' }).click()
    })

    expect(screen.getByTestId('cart-count')).toHaveTextContent('0')
  })
})