import React from 'react'
import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StoreItem from './StoreItem'
import { StoreContext } from '../context/StoreContext'

const product =
{
  id: 1,
  name: 'Apple',
  image: '/apple.jpeg',
  price: '2.50',
  weight: '1',
  available: true,
}

const renderStoreItem = (props = product) =>
{
  return render(
    <MemoryRouter>
      <StoreContext.Provider value={{ currency: '$' }}>
        <StoreItem {...props} />
      </StoreContext.Provider>
    </MemoryRouter>
  )
}

describe('StoreItem', () => {
  test('shows name, price, and weight', () => {
    renderStoreItem()

    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.getByText('$2.50')).toBeInTheDocument()
    expect(screen.getByText('1 lb')).toBeInTheDocument()
  })

  test('links to the correct item page', () => {
    renderStoreItem()

    expect(screen.getByRole('link')).toHaveAttribute('href', '/item/1')
  })

  test('shows Unavailable when the item is out of stock', () => {
    renderStoreItem({ ...product, available: false })

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  test('does not show Unavailable when the item is available', () => {
    renderStoreItem()

    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
  })
})