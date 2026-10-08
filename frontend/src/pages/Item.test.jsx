import React from 'react'
import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Item from './Item'
import { StoreContext } from '../context/StoreContext'

vi.mock('../components/RelatedItems', () =>
({
  default: () => <div />,
}))

const products =
[
  {
    product_id: 1,
    name: 'Apple',
    image: '/apple.jpeg',
    price: '2.50',
    unit_weight_lb: '1.00',
    description: 'Fresh apple',
    category: 'Fruit',
    stock: 5,
    available: true,
  },
  {
    product_id: 2,
    name: 'Milk',
    image: '/milk.jpeg',
    price: '3.00',
    unit_weight_lb: '2.00',
    description: 'Fresh milk',
    category: 'Dairy',
    stock: 0,
    available: false,
  },
]

const renderItem = (itemId) =>
{
  const contextValue =
  {
    products,
    currency: '$',
    shoppingCartItems: {},
    addToCart: vi.fn(),
  }

  return render(
    <StoreContext.Provider value={contextValue}>
      <MemoryRouter initialEntries={[`/item/${itemId}`]}>
        <Routes>
          <Route path="/item/:itemId" element={<Item />} />
        </Routes>
      </MemoryRouter>
    </StoreContext.Provider>
  )
}

describe('Item', () =>
{
  test('shows ADD TO CART when the item is available', () =>
  {
    renderItem(1)

    expect(screen.getByRole('button', { name: 'ADD TO CART' })).toBeInTheDocument()
  })

  test('shows Currently unavailable when the item is unavailable', () =>
  {
    renderItem(2)

    expect(screen.getByText('Currently unavailable')).toBeInTheDocument()
  })

  test('does not render an item when the id is invalid', () =>
  {
    renderItem(999)

    expect(screen.queryByRole('button', { name: 'ADD TO CART' })).not.toBeInTheDocument()
    expect(screen.queryByText('Currently unavailable')).not.toBeInTheDocument()
  })
})