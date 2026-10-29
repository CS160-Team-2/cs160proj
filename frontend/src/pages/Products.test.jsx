import React from 'react'
import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Products from './Products'
import { StoreContext } from '../context/StoreContext'

const product = (product_id, name, category, price) => ({
  product_id,
  name,
  category,
  price,
  image: `/${product_id}.jpeg`,
  unit_weight_lb: '1.00',
  description: '',
  stock: 5,
  available: true,
})

const products = [
  product(1, 'Fuji Apple', 'Fruits', '2.50'),
  product(2, 'Green Apple', 'Fruits', '6.00'),
  product(3, 'Broccoli Crown', 'Vegetables', '2.99'),
]

const renderProducts = () =>
  render(
    <MemoryRouter>
      <StoreContext.Provider value={{ products, productsLoading: false, currency: '$' }}>
        <Products />
      </StoreContext.Provider>
    </MemoryRouter>
  )

describe('Products search', () => {
  test('narrows the list as the shopper types, ignoring capitals', async () => {
    const user = userEvent.setup()
    renderProducts()

    await user.type(screen.getByLabelText('Search products'), 'APPLE')

    expect(screen.getByText('Fuji Apple')).toBeInTheDocument()
    expect(screen.getByText('Green Apple')).toBeInTheDocument()
    expect(screen.queryByText('Broccoli Crown')).not.toBeInTheDocument()
  })

  test('works together with the category filter', async () => {
    const user = userEvent.setup()
    renderProducts()

    await user.type(screen.getByLabelText('Search products'), 'c')
    await user.click(screen.getByLabelText('Vegetables'))
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }))

    expect(screen.getByText('Broccoli Crown')).toBeInTheDocument()
    expect(screen.queryByText('Fuji Apple')).not.toBeInTheDocument()
  })

  test('says so when nothing matches, and clearing brings everything back', async () => {
    const user = userEvent.setup()
    renderProducts()

    await user.type(screen.getByLabelText('Search products'), 'mango')
    expect(screen.getByText('No products match "mango".')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear search' }))

    expect(screen.getByLabelText('Search products')).toHaveValue('')
    expect(screen.getAllByText(/Apple|Broccoli/)).toHaveLength(3)
  })
})
