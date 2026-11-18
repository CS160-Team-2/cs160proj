import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, Link } from 'react-router-dom'
import StoreContextProvider from '../context/StoreContext'
import Inventory from './Inventory'
import Item from './Item'
import { api } from '../api'

vi.mock('../api', () => ({ api: vi.fn() }))

const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }
const emptyCart = { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false }

// One shared "database": the staff API and the shop API read and write the same product, like the real backend.
let apple

// The shop's view of the product, the way /api/products shapes it.
const shopView = () => ({
  product_id: 1, name: apple.name, description: 'Crisp', category: 'Fruits', price: apple.price,
  unit_weight_lb: '1.00', image_key: 'apple', stock: apple.stock, available: apple.listed && apple.stock > 0,
})

// Answers both the staff inventory API and the shop API from the same apple.
function mockBackend() {
  apple = { name: 'Apple', price: '2.50', stock: 5, listed: true }
  api.mockImplementation(async (path, options = {}) => {
    const { method = 'GET', body } = options
    if (path === '/api/auth/me') return { user: employee }
    if (path === '/api/cart') return { cart: emptyCart }
    if (path === '/api/categories') return { categories: ['Fruits'] }
    if (path === '/api/products') return { products: apple.listed ? [shopView()] : [] }
    if (path === '/api/products/1') return { product: shopView() }
    if (path.startsWith('/api/admin/inventory/') && method === 'PATCH') {
      apple.stock += body.delta
      return { product: { product_id: 1, ...apple, category: 'Fruits', unit_weight_lb: '1.00', is_listed: apple.listed, low_stock: false, available: true } }
    }
    if (path === '/api/admin/products/1' && method === 'DELETE') { apple.listed = false; return { ok: true } }
    if (path === '/api/admin/products/1' && method === 'PATCH') { Object.assign(apple, { name: body.name ?? apple.name, price: body.price ?? apple.price, listed: body.is_listed ?? apple.listed }); return { product: {} } }
    if (path.startsWith('/api/admin/inventory')) {
      return { inventory: [{ product_id: 1, name: apple.name, description: 'Crisp', category: 'Fruits', price: apple.price, unit_weight_lb: '1.00', is_listed: apple.listed, stock: apple.stock, low_stock: false, available: apple.stock > 0, image_key: 'apple' }] }
    }
    throw new Error(`Unexpected API request: ${method} ${path}`)
  })
}

// Draws the staff console and the product page in one app, with a link to go between them.
function renderApp() {
  render(
    <MemoryRouter initialEntries={['/inventory']}>
      <StoreContextProvider>
        <Link to="/item/1">Go to the apple page</Link>
        <Routes>
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/item/:itemId" element={<Item />} />
        </Routes>
      </StoreContextProvider>
    </MemoryRouter>,
  )
}

describe('what staff change in the inventory console shows in the shop', () => {
  beforeEach(() => { vi.resetAllMocks(); mockBackend() })

  test('adding 10 to the apples makes the apple page show 15 without reloading the site', async () => {
    const user = userEvent.setup()
    renderApp()
    await screen.findByLabelText('Change stock of Apple')

    await user.type(screen.getByLabelText('Change stock of Apple'), '10')
    await user.click(screen.getByRole('button', { name: 'UPDATE' }))
    await waitFor(() => expect(api.mock.calls.filter(([path]) => path === '/api/products').length).toBeGreaterThan(1))
    await user.click(screen.getByRole('link', { name: 'Go to the apple page' }))

    expect(await screen.findByText('15')).toBeInTheDocument()
  })

  test('unlisting a product removes it from the shop straight away', async () => {
    const user = userEvent.setup()
    renderApp()
    await screen.findByLabelText('Change stock of Apple')

    await user.click(screen.getByRole('button', { name: 'UNLIST' }))
    await waitFor(() => expect(api.mock.calls.filter(([path]) => path === '/api/products').length).toBeGreaterThan(1))
    await user.click(screen.getByRole('link', { name: 'Go to the apple page' }))

    expect(await screen.findByText(/could not find that product|not found/i)).toBeInTheDocument()
  })
})

describe('the shop keeps its stock fresh on its own', () => {
  beforeEach(() => { vi.resetAllMocks(); mockBackend(); vi.useFakeTimers({ shouldAdvanceTime: true }) })

  test('a change made elsewhere appears after 30 seconds, and when the tab is shown again', async () => {
    render(
      <MemoryRouter initialEntries={['/item/1']}>
        <StoreContextProvider><Routes><Route path="/item/:itemId" element={<Item />} /></Routes></StoreContextProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('5')).toBeInTheDocument()

    apple.stock = 9
    await act(async () => { await vi.advanceTimersByTimeAsync(30500) })
    expect(await screen.findByText('9')).toBeInTheDocument()

    apple.stock = 12
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(await screen.findByText('12')).toBeInTheDocument()
    vi.useRealTimers()
  })
})
