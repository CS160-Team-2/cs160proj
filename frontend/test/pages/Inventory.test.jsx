import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import Inventory from '../../src/pages/Inventory'
import { api } from '../../src/api'
import { renderWithProviders } from '../renderWithProviders'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

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
  low_stock_threshold: 2,
  ...fields,
})

const view = (product) => ({
  ...product,
  low_stock: product.stock <= product.low_stock_threshold,
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
      if (body.delta !== undefined && apple.stock + body.delta < 0) {
        throw new Error(`Stock cannot go below zero: there are only ${apple.stock} in stock`)
      }
      if (body.delta !== undefined) apple.stock += body.delta
      if (body.low_stock_threshold !== undefined) apple.low_stock_threshold = body.low_stock_threshold
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

    if (path.startsWith('/api/admin/inventory/1/changes')) {
      return { changes: [
        { log_id: 3, change_qty: -2, old_quantity: 7, new_quantity: 5, reason: 'Sold on order OFS-ABC123', created_at: '2026-11-20T10:00:00', changed_by: null, order_number: 'OFS-ABC123' },
        { log_id: 2, change_qty: 4, old_quantity: 3, new_quantity: 7, reason: 'Delivery received', created_at: '2026-11-19T09:00:00', changed_by: 'Eli Park', order_number: null },
      ] }
    }
    if (path === '/api/admin/categories') return { categories: ['Fruits', 'Seafood'] }
    if (path === '/api/admin/products/1/image' && method === 'POST') throw new Error('The picture is larger than 5 MB.')

    if (path.startsWith('/api/admin/inventory')) {
      const category = new URLSearchParams(path.split('?')[1] || '').get('category')
      return { inventory: products.filter((p) => !category || p.category === category).map(view) }
    }

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
    expect(screen.getByText(/Fruits · /)).toBeInTheDocument()
    expect(screen.getByText(/\$2\.50/)).toBeInTheDocument()
    expect(screen.getByText(/1\.00 lb/)).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  test('adding stock sends the change and shows the new amount', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '10')
    await user.selectOptions(screen.getByLabelText('Reason for changing stock of Apple'), 'Delivery received')
    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))

    expect(await screen.findByText('15')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/inventory/1', {
      method: 'PATCH',
      body: { delta: 10, reason: 'Delivery received' },
    })
  })

  test('shows the backend message when stock would go below zero', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '-9')
    await user.selectOptions(screen.getByLabelText('Reason for changing stock of Apple'), 'Damaged or spoiled')
    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))

    expect(
      await screen.findByText('Stock cannot go below zero: there are only 5 in stock')
    ).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  test('asks for a number when the box is empty', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))

    expect(screen.getByText('Enter a number such as 10 or -3.')).toBeInTheDocument()
  })

  // E2: the employee must say why the stock changed.
  test('will not change the stock without a reason', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '4')
    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))

    expect(screen.getByText('Choose a reason for the change.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/inventory/1', expect.anything())
  })

  test('"Other" asks for a few words and sends them as the reason', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '-2')
    await user.selectOptions(screen.getByLabelText('Reason for changing stock of Apple'), 'Other')
    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))
    expect(screen.getByText('Write a few words for the reason.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Other reason for changing stock of Apple'), 'dropped on the floor')
    await user.click(screen.getByRole('button', { name: 'Update stock of Apple' }))

    expect(api).toHaveBeenCalledWith('/api/admin/inventory/1', { method: 'PATCH', body: { delta: -2, reason: 'Other: dropped on the floor' } })
    expect(await screen.findByText('3')).toBeInTheDocument()
  })

  // E3: the low-stock level of each product can be seen and changed.
  test('shows each product low-stock level and saves a new one', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    const level = screen.getByLabelText('Low-stock level of Apple')
    expect(level).toHaveValue(2)
    expect(screen.queryByRole('button', { name: 'Save low-stock level of Apple' })).not.toBeInTheDocument()

    await user.clear(level)
    await user.type(level, '8')
    await user.click(screen.getByRole('button', { name: 'Save low-stock level of Apple' }))

    expect(api).toHaveBeenCalledWith('/api/admin/inventory/1', { method: 'PATCH', body: { low_stock_threshold: 8 } })
    expect(await screen.findByText('LOW')).toBeInTheDocument()       // 5 in stock is now at or below 8
  })

  test('refuses a low-stock level that is not a whole number', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    const level = screen.getByLabelText('Low-stock level of Apple')

    await user.clear(level)
    await user.type(level, '-3')
    await user.click(screen.getByRole('button', { name: 'Save low-stock level of Apple' }))

    expect(screen.getByText('Enter a whole number, 0 or more.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/inventory/1', expect.objectContaining({ method: 'PATCH' }))
  })

  // E4: filter the list by category.
  test('filters the inventory by category', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    await user.selectOptions(screen.getByLabelText('Filter by category'), 'Fruits')

    expect(api).toHaveBeenCalledWith('/api/admin/inventory?category=Fruits')
    await user.selectOptions(screen.getByLabelText('Filter by category'), '')
    expect(api).toHaveBeenLastCalledWith('/api/admin/inventory?')
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
    await user.selectOptions(screen.getByLabelText('Category'), 'Fruits')
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

  // E5: every product has a history of its stock changes.
  test('shows the stock history: when, who, how much, the new stock and why', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    expect(screen.queryByRole('table', { name: 'Stock history of Apple' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'History of Apple' }))

    const table = await screen.findByRole('table', { name: 'Stock history of Apple' })
    expect(table).toHaveTextContent('Eli Park')
    expect(table).toHaveTextContent('+4')
    expect(table).toHaveTextContent('Delivery received')
    expect(table).toHaveTextContent('Sold on order OFS-ABC123')
    expect(table).toHaveTextContent('Customer order')
    expect(table).toHaveTextContent('-2')
    await user.click(screen.getByRole('button', { name: 'History of Apple' }))
    expect(screen.queryByRole('table', { name: 'Stock history of Apple' })).not.toBeInTheDocument()
  })

  // E6: a short description under each product's name.
  test('shows the description under the product name', async () => {
    renderWithProviders(<Inventory />, { route: '/inventory' })

    expect(await screen.findByText('Crisp and sweet')).toBeInTheDocument()
  })

  // EB1: if the picture fails after the details were saved, the list is refreshed and the form stays open.
  test('when the picture upload fails the details are still saved, the list refreshes and the form stays open', async () => {
    const user = userEvent.setup()
    URL.createObjectURL = vi.fn(() => 'blob:preview')       // jsdom has no picture previews
    URL.revokeObjectURL = vi.fn()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    const loads = () => api.mock.calls.filter(([path]) => String(path).startsWith('/api/admin/inventory?')).length
    const before = loads()

    await user.click(screen.getByRole('button', { name: 'EDIT' }))
    await user.clear(screen.getByPlaceholderText('Price (required)'))
    await user.type(screen.getByPlaceholderText('Price (required)'), '3.10')
    await user.upload(screen.getByLabelText('Product picture'), new File(['x'], 'big.png', { type: 'image/png' }))
    await user.click(screen.getByRole('button', { name: 'SAVE' }))

    expect(await screen.findByText(/Saved, but the picture was not saved: The picture is larger than 5 MB\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SAVE' })).toBeInTheDocument()
    expect(Number(products[0].price)).toBe(3.1)
    expect(loads()).toBeGreaterThan(before)
  })

  // EB2: the category list includes categories that only unlisted products have.
  test('offers every category in the filter, even one no product on screen has', async () => {
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')

    expect(await screen.findByRole('option', { name: 'Seafood' })).toBeInTheDocument()
  })

  // ET3: the add form checks its fields before asking the server.
  test('will not add a product with a price of zero, or without a category', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))
    await user.type(screen.getByLabelText('Product name'), 'Pear')
    await user.type(screen.getByLabelText('Price'), '0')
    await user.type(screen.getByLabelText('Weight in lb'), '2')
    await user.click(screen.getByRole('button', { name: 'ADD' }))
    expect(screen.getByText('Enter a price greater than 0.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Price'))
    await user.type(screen.getByLabelText('Price'), '3.25')
    await user.click(screen.getByRole('button', { name: 'ADD' }))
    expect(screen.getByText('Choose a category.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/products', expect.anything())
  })

  test('shows the server message when the name is already taken and keeps the form open', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    const normal = api.getMockImplementation()
    api.mockImplementation(async (path, options = {}) => {
      if (path === '/api/admin/products' && options.method === 'POST') throw new Error('A product called "Apple" already exists. Choose another name.')
      return normal(path, options)
    })
    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))
    await user.type(screen.getByLabelText('Product name'), 'apple')
    await user.selectOptions(screen.getByLabelText('Category'), 'Fruits')
    await user.type(screen.getByLabelText('Price'), '3.25')
    await user.type(screen.getByLabelText('Weight in lb'), '2')
    await user.click(screen.getByRole('button', { name: 'ADD' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A product called "Apple" already exists. Choose another name.')
    expect(screen.getByLabelText('Product name')).toHaveValue('apple')
  })

  // ET2: the picture is checked in the browser before it is sent.
  test('refuses a picture of the wrong type before sending it', async () => {
    const user = userEvent.setup({ applyAccept: false })
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))

    await user.upload(screen.getByLabelText('Product picture'), new File(['<svg></svg>'], 'logo.svg', { type: 'image/svg+xml' }))

    expect(screen.getByText('The picture must be a JPEG, PNG or WebP file.')).toBeInTheDocument()
  })

  test('refuses a picture over 5 MB before sending it', async () => {
    const user = userEvent.setup({ applyAccept: false })
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText('Apple')
    await user.click(screen.getByRole('button', { name: 'ADD PRODUCT' }))
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 5 * 1024 * 1024 + 1 })

    await user.upload(screen.getByLabelText('Product picture'), big)

    expect(screen.getByText('The picture must be 5 MB or smaller.')).toBeInTheDocument()
  })

  // ET9: a product name with markup is shown as plain text, never run.
  test('shows a product name that looks like HTML as plain text', async () => {
    mockApi()
    products[0].name = '<img src=x onerror="alert(1)"> Apple'
    renderWithProviders(<Inventory />, { route: '/inventory' })

    expect(await screen.findByText('<img src=x onerror="alert(1)"> Apple')).toBeInTheDocument()
    expect(document.querySelector('img[onerror]')).toBeNull()
  })
})
