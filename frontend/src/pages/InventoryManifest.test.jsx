import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Inventory from './Inventory'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))

const manager = { user_id: 3, full_name: 'Maya Chen', role: 'manager' }
const employee = { user_id: 2, full_name: 'Eli Park', role: 'employee' }

const emptyCart = {
  items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00',
  delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false,
}

const csv = (text, name = 'delivery.csv') => new File([text], name, { type: 'text/csv' })

const cleanPreview = {
  filename: 'delivery.csv',
  lines: [
    { line_numbers: [2], product_id: 1, name: 'Organic Apples, 3 lb bag', quantity: 24, stock_now: 40, stock_after: 64, is_listed: true },
    { line_numbers: [3, 5], product_id: 3, name: 'Organic Broccoli Crown', quantity: 30, stock_now: 35, stock_after: 65, is_listed: false },
  ],
  problems: [],
  can_apply: true,
  already_applied: null,
}

// What the fake backend answers for a preview and an apply; each test
// sets what it needs.
let preview
let applyResult

function mockApi(signedInUser = manager) {
  preview = cleanPreview
  applyResult = { manifest: { manifest_id: 12, filename: 'delivery.csv', line_count: 2, total_units: 54 } }
  api.mockImplementation(async (path, options = {}) => {
    const { method = 'GET' } = options

    if (path === '/api/auth/me') return { user: signedInUser }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }
    if (path === '/api/categories') return { categories: [] }
    if (path.startsWith('/api/admin/inventory?')) return { inventory: [] }

    if (path === '/api/admin/inventory/manifest/preview' && method === 'POST') return preview
    if (path === '/api/admin/inventory/manifest' && method === 'POST') {
      if (applyResult instanceof Error) throw applyResult
      return applyResult
    }

    throw new Error(`Unexpected API request: ${method} ${path}`)
  })
}

const chooseFile = async (user, file = csv('product_name,quantity\n')) => {
  await user.upload(await screen.findByLabelText('Delivery manifest file'), file)
}

describe('Delivery manifest upload', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi()
  })

  test('managers see the upload', async () => {
    renderWithProviders(<Inventory />, { route: '/inventory' })
    expect(await screen.findByLabelText('Delivery manifest file')).toBeInTheDocument()
  })

  test('employees do not see the upload', async () => {
    mockApi(employee)
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await screen.findByText(/INVENTORY/)
    expect(screen.queryByLabelText('Delivery manifest file')).not.toBeInTheDocument()
  })

  test('choosing a file sends it for a preview', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    const file = csv('product_name,quantity\nOrganic Broccoli Crown,30\n')

    await chooseFile(user, file)

    const call = api.mock.calls.find(([path]) => path === '/api/admin/inventory/manifest/preview')
    expect(call[1].method).toBe('POST')
    expect(call[1].body).toBeInstanceOf(FormData)
    expect(call[1].body.get('file')).toBe(file)
  })

  test('the preview shows stock now and after for each product', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })

    await chooseFile(user)

    const apples = await screen.findByRole('row', { name: /Organic Apples, 3 lb bag/ })
    expect(apples).toHaveTextContent('40')
    expect(apples).toHaveTextContent('+24')
    expect(apples).toHaveTextContent('64')
    const broccoli = screen.getByRole('row', { name: /Organic Broccoli Crown/ })
    expect(broccoli).toHaveTextContent('lines 3, 5')
    expect(broccoli).toHaveTextContent('UNLISTED')
    expect(screen.getByRole('button', { name: 'APPLY MANIFEST' })).toBeEnabled()
  })

  test('problems are listed by line and the manifest cannot be applied', async () => {
    preview = {
      ...cleanPreview,
      lines: [],
      problems: [
        { line: 3, message: 'No product named "Organic Brocoli Crown"' },
        { line: 5, message: 'Quantity must be a whole number from 1 to 100000' },
      ],
      can_apply: false,
    }
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })

    await chooseFile(user)

    expect(await screen.findByText(/Line 3: No product named "Organic Brocoli Crown"/)).toBeInTheDocument()
    expect(screen.getByText(/Line 5: Quantity must be a whole number/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'APPLY MANIFEST' })).not.toBeInTheDocument()
  })

  test('a file that was already applied says so and cannot be applied again', async () => {
    preview = {
      ...cleanPreview,
      can_apply: false,
      already_applied: { manifest_id: 7, applied_by: 'Maya Chen', applied_at: '2026-11-03T09:30:00' },
    }
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })

    await chooseFile(user)

    expect(await screen.findByText(/already applied as manifest #7 by Maya Chen/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'APPLY MANIFEST' })).not.toBeInTheDocument()
  })

  test('applying saves it, confirms, and reloads the inventory', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await chooseFile(user)
    const loadsBefore = api.mock.calls.filter(([path]) => path.startsWith('/api/admin/inventory?')).length

    await user.click(await screen.findByRole('button', { name: 'APPLY MANIFEST' }))

    expect(api.mock.calls.some(([path, options]) =>
      path === '/api/admin/inventory/manifest' && options.body instanceof FormData)).toBe(true)
    expect(await screen.findByText('Added 54 units from delivery.csv (manifest #12).')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'APPLY MANIFEST' })).not.toBeInTheDocument()
    const loadsAfter = api.mock.calls.filter(([path]) => path.startsWith('/api/admin/inventory?')).length
    expect(loadsAfter).toBeGreaterThan(loadsBefore)
  })

  test('if applying fails, the message is shown and nothing is claimed', async () => {
    applyResult = new Error('This delivery manifest was already applied')
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await chooseFile(user)

    await user.click(await screen.findByRole('button', { name: 'APPLY MANIFEST' }))

    expect(await screen.findByText('This delivery manifest was already applied')).toBeInTheDocument()
    expect(screen.queryByText(/^Added \d+ units/)).not.toBeInTheDocument()
  })

  test('cancel clears the preview', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Inventory />, { route: '/inventory' })
    await chooseFile(user)
    await screen.findByRole('button', { name: 'APPLY MANIFEST' })

    await user.click(screen.getByRole('button', { name: 'CANCEL MANIFEST' }))

    expect(screen.queryByRole('row', { name: /Organic Apples/ })).not.toBeInTheDocument()
  })
})
