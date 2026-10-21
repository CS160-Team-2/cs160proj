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

// The fake backend keeps a list of products. Stock changes, edits, new
// products and unlisting all change this list, like the real database.
let products

const newProduct = (fields) => ({
  product_id: 1,
  name: 'Apple',
  description: 'Crisp and sweet',
  category: 'Fruits',
  price: '2.50',
  unit_weight_lb: '1.00',
  is_listed: true,
  stock: 5,
  ...fields,
})

const view = (product) => ({
  ...product,
  low_stock: product.stock <= 2,
  available: product.is_listed && product.stock > 0,
})

function mockApi(signedInUser = employee) {
  products = [newProduct()]
  api.mockImplementation(async (path, options = {}) => {
    const { method = 'GET', body } = options

    if (path === '/api/auth/me') return { user: signedInUser }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }

    if (path.startsWith('/api/admin/inventory/') && method === 'PATCH') {
      const apple = products[0]
      if (apple.stock + body.delta < 0) {
        throw new Error(`Stock cannot go below zero: there are only ${apple.stock} in stock`)
      }
      apple.stock += body.delta
      return { product: view(apple) }
    }

    if (path === '/api/admin/products' && method === 'POST') {
      const created = newProduct({
        product_id: products.length + 1,
        name: body.name,
        category: body.category || 'Other',
        price: body.price,
        unit_weight_lb: body.unit_weight_lb,
        description: body.description || null,
        stock: body.initial_stock,
      })
      products.push(created)
      return { product: view(created) }
    }

    if (path === '/api/admin/products/1' && method === 'PATCH') {
      Object.assign(products[0], body)
      return { product: view(products[0]) }
    }

    if (path === '/api/admin/products/1' && method === 'DELETE') {
      products[0].is_listed = false
      return { product: view(products[0]) }
    }

    if (path.startsWith('/api/admin/inventory')) return { inventory: products.map(view) }

    throw new Error(`Unexpected API request: ${method} ${path}`)
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

  test('adds a new product with its weight and starting stock', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))
    await user.type(screen.getByLabelText('Product name'), 'Pear')
    await user.type(screen.getByLabelText('Category'), 'Fruits')
    await user.type(screen.getByLabelText('Price'), '3.25')
    await user.type(screen.getByLabelText('Weight in lb'), '0.5')
    await user.type(screen.getByLabelText('Starting stock'), '12')
    await user.click(screen.getByRole('button', { name: 'ADD' }))

    expect(await screen.findByText('Pear')).toBeInTheDocument()
    expect(screen.getByText('Added Pear.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/products', {
      method: 'POST',
      body: { name: 'Pear', category: 'Fruits', price: '3.25', unit_weight_lb: '0.5', initial_stock: 12 },
    })
  })

  test('will not add a product without a weight', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))
    await user.type(screen.getByLabelText('Product name'), 'Pear')
    await user.type(screen.getByLabelText('Price'), '3.25')
    await user.click(screen.getByRole('button', { name: 'ADD' }))

    expect(screen.getByText('Weight is required and must be greater than 0.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/products', expect.anything())
  })

  test('edits a product price and weight', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'EDIT' }))
    const price = screen.getByLabelText('Price')
    const weight = screen.getByLabelText('Weight in lb')
    await user.clear(price)
    await user.type(price, '2.75')
    await user.clear(weight)
    await user.type(weight, '1.25')
    await user.click(screen.getByRole('button', { name: 'SAVE' }))

    expect(await screen.findByText(/\$2\.75/)).toBeInTheDocument()
    expect(screen.getByText(/1\.25 lb/)).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/products/1', {
      method: 'PATCH',
      body: {
        name: 'Apple',
        category: 'Fruits',
        price: '2.75',
        unit_weight_lb: '1.25',
        description: 'Crisp and sweet',
      },
    })
  })

  test('will not save an edit with the weight removed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'EDIT' }))
    await user.clear(screen.getByLabelText('Weight in lb'))
    await user.click(screen.getByRole('button', { name: 'SAVE' }))

    expect(screen.getByText('Weight is required and must be greater than 0.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/products/1', expect.anything())
  })

  test('cancelling an edit closes the form without saving', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'EDIT' }))
    await user.click(screen.getByRole('button', { name: 'CANCEL' }))

    expect(screen.queryByText('Edit product')).not.toBeInTheDocument()
    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/products/1', expect.anything())
  })

  test('unlisting a product hides it from the shop, and it can be listed again', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'UNLIST' }))

    expect(await screen.findByText('UNLISTED')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/products/1', { method: 'DELETE' })

    await user.click(screen.getByRole('button', { name: 'LIST AGAIN' }))

    expect(await screen.findByRole('button', { name: 'UNLIST' })).toBeInTheDocument()
    expect(screen.queryByText('UNLISTED')).not.toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/products/1', {
      method: 'PATCH',
      body: { is_listed: true },
    })
  })
})
