import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import Inventory from './Inventory'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))

const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }
const customer = { user_id: 1, full_name: 'Anna Rivera', role: 'customer' }

const emptyCart = {
  items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00',
  delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false,
}

// The fake backend keeps one product whose stock changes when it is patched.
let stock

const apple = () => ({
  product_id: 1,
  name: 'Apple',
  category: 'Fruits',
  price: '2.50',
  unit_weight_lb: '1.00',
  is_listed: true,
  stock,
  low_stock: stock <= 2,
  available: stock > 0,
})

function mockApi(signedInUser = employee) {
  stock = 5
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/auth/me') return { user: signedInUser }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }

    if (path.startsWith('/api/admin/inventory/') && options.method === 'PATCH') {
      if (stock + options.body.delta < 0) {
        throw new Error(`Stock cannot go below zero: there are only ${stock} in stock`)
      }
      stock += options.body.delta
      return { product: apple() }
    }

    if (path.startsWith('/api/admin/inventory')) return { inventory: [apple()] }

    throw new Error(`Unexpected API request: ${options.method || 'GET'} ${path}`)
  })
}

describe('Inventory', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('shows each product with its price, weight and stock', async () => {
    renderWithProviders(<Inventory />, { route: '/inventory' })

    expect(await screen.findByText('Apple')).toBeInTheDocument()
    expect(screen.getByText(/Fruits/)).toBeInTheDocument()
    expect(screen.getByText(/\$2\.50/)).toBeInTheDocument()
    expect(screen.getByText(/1\.00 lb/)).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  test('adding stock sends the change and shows the new amount', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '10')
    await user.click(screen.getByRole('button', { name: 'UPDATE' }))

    expect(await screen.findByText('15')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/inventory/1', {
      method: 'PATCH',
      body: { delta: 10, reason: 'Restock' },
    })
  })

  test('shows the backend message when stock would go below zero', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '-9')
    await user.click(screen.getByRole('button', { name: 'UPDATE' }))

    expect(
      await screen.findByText('Stock cannot go below zero: there are only 5 in stock')
    ).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  test('asks for a number when the box is empty', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'UPDATE' }))

    expect(screen.getByText('Enter a number such as 10 or -3.')).toBeInTheDocument()
  })

  test('searching asks the backend for matching products', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByPlaceholderText('Search products'), 'app')

    expect(api).toHaveBeenCalledWith('/api/admin/inventory?search=app')
  })

  test('sends a customer to the login page instead', async () => {
    mockApi(customer)
    renderWithProviders(
      <Routes>
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/login" element={<p>Login page</p>} />
      </Routes>,
      { route: '/inventory' }
    )

    expect(await screen.findByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Apple')).not.toBeInTheDocument()
  })
})