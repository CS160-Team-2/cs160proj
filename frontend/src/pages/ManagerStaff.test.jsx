import React from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import ManagerStaff from './ManagerStaff'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api', () => ({ api: vi.fn() }))

const manager = { user_id: 3, full_name: 'Mia Chen', email: 'manager@ofs.test', role: 'manager' }
const employee = { user_id: 2, full_name: 'Eli Park', email: 'employee@ofs.test', role: 'employee' }
const customer = { user_id: 1, full_name: 'Anna Rivera', role: 'customer' }
const emptyCart = { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false }
const account = (user, fields = {}) => ({ ...user, is_active: true, phone: null, created_at: '2026-11-08T10:00:00', ...fields })
let staff

const mockApi = (signedIn = manager) => {
  staff = [account(manager), account(employee)]
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/auth/me') return { user: signedIn }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: emptyCart }
    if (path === '/api/admin/staff' && (!options.method || options.method === 'GET')) return { staff: staff.map((row) => ({ ...row })) }
    if (path === '/api/admin/staff' && options.method === 'POST') {
      const { password, ...fields } = options.body
      const created = account({ user_id: 10, ...fields, email: fields.email.toLowerCase() })
      staff.push(created)
      return { staff: created }
    }
    const match = path.match(/^\/api\/admin\/staff\/(\d+)$/)
    if (match) {
      const row = staff.find((entry) => entry.user_id === Number(match[1]))
      if (!row) throw new Error('No staff account with that id')
      if (options.method === 'PATCH') Object.assign(row, options.body)
      else if (options.method === 'DELETE') row.is_active = false
      else throw new Error(`Unexpected method ${options.method}`)
      return { staff: { ...row } }
    }
    throw new Error(`Unexpected API request: ${path}`)
  })
}

const show = () => renderWithProviders(<ManagerStaff />, { route: '/manager/staff' })
const enterNewStaff = async (user, role = 'employee') => {
  await user.click(screen.getByRole('button', { name: 'Add staff account' }))
  await user.type(screen.getByLabelText('Full name'), 'New Clerk')
  await user.type(screen.getByLabelText('Email'), 'clerk@ofs.test')
  await user.type(screen.getByLabelText('Initial password', { exact: false }), 'initial-pass-1')
  await user.selectOptions(screen.getByLabelText('Role', { exact: true }), role)
}

beforeEach(() => { vi.resetAllMocks(); mockApi() })

describe('ManagerStaff', () => {
  test('lists staff contact, role and active state without a password field', async () => {
    show()
    expect(await screen.findByRole('table', { name: 'Staff accounts and access' })).toBeInTheDocument()
    const employeeRow = screen.getByRole('row', { name: /Eli Park/ })
    expect(employeeRow).toHaveTextContent('employee@ofs.test')
    expect(employeeRow).toHaveTextContent('Employee')
    expect(employeeRow).toHaveTextContent('Active')
    expect(screen.queryByLabelText(/Initial password/)).not.toBeInTheDocument()
  })

  test.each(['employee', 'manager'])('creates a %s account and clears the initial password after success', async (role) => {
    const user = userEvent.setup()
    show()
    await screen.findByText('Eli Park')
    await enterNewStaff(user, role)
    await user.click(screen.getByRole('button', { name: 'Create staff account' }))
    expect(await screen.findByText('Created New Clerk.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/staff', { method: 'POST', body: {
      full_name: 'New Clerk', email: 'clerk@ofs.test', phone: null, role, password: 'initial-pass-1',
    } })
    expect(screen.getByRole('row', { name: /New Clerk/ })).toHaveTextContent('clerk@ofs.test')
    expect(screen.queryByLabelText(/Initial password/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add staff account' }))
    expect(screen.getByLabelText('Initial password', { exact: false })).toHaveValue('')
  })

  test('cancelling creation clears password state before reopening', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('Eli Park')
    await enterNewStaff(user)
    await user.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
    expect(api.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Add staff account' }))
    expect(screen.getByLabelText('Initial password', { exact: false })).toHaveValue('')
    expect(screen.getByLabelText('Full name')).toHaveValue('')
  })

  test('edits staff details and promotes an employee without sending a password', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'Edit Eli Park' }))
    await user.clear(screen.getByLabelText('Full name'))
    await user.type(screen.getByLabelText('Full name'), 'Eli Park Jr')
    await user.type(screen.getByLabelText('Phone (optional)'), '408-555-0100')
    await user.selectOptions(screen.getByLabelText('Role', { exact: true }), 'manager')
    expect(screen.queryByLabelText(/Initial password/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save staff changes' }))
    expect(await screen.findByText('Updated Eli Park Jr.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/staff/2', { method: 'PATCH', body: {
      full_name: 'Eli Park Jr', email: 'employee@ofs.test', phone: '408-555-0100', role: 'manager',
    } })
    expect(screen.getByRole('row', { name: /Eli Park Jr/ })).toHaveTextContent('Manager')
  })

  test('requires confirmation to deactivate and can reactivate the preserved account', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'Deactivate Eli Park' }))
    expect(screen.getByRole('dialog', { name: 'Deactivate Eli Park?' })).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/staff/2', { method: 'DELETE' })
    await user.click(screen.getByRole('button', { name: 'Cancel deactivation' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Deactivate Eli Park' }))
    await user.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
    expect(await screen.findByText('Deactivated Eli Park.')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Eli Park/ })).toHaveTextContent('Inactive')
    await user.click(screen.getByRole('button', { name: 'Reactivate Eli Park' }))
    expect(await screen.findByText('Reactivated Eli Park.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/staff/2', { method: 'PATCH', body: { is_active: true } })
    expect(within(screen.getByRole('row', { name: /Eli Park/ })).getByText('Active', { exact: true })).toBeInTheDocument()
  })

  test('disables deactivation and role changes for the signed-in manager', async () => {
    const user = userEvent.setup()
    show()
    expect(await screen.findByRole('button', { name: 'Deactivate Mia Chen' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Edit Mia Chen' }))
    expect(screen.getByLabelText('Role', { exact: true })).toBeDisabled()
    expect(screen.getByLabelText('Full name')).toBeEnabled()
  })

  test('protects the sole active manager even when another manager account is inactive', async () => {
    const user = userEvent.setup()
    // A stale list must not offer to remove its only known active manager.
    mockApi({ ...manager, user_id: 99 })
    staff.push(account({ user_id: 4, full_name: 'Inactive Manager', email: 'inactive@ofs.test', role: 'manager' }, { is_active: false }))
    show()
    expect(await screen.findByRole('button', { name: 'Deactivate Mia Chen' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Edit Mia Chen' }))
    expect(screen.getByLabelText('Role', { exact: true })).toBeDisabled()
  })

  test('keeps the form and displays backend validation errors', async () => {
    const fallback = api.getMockImplementation()
    api.mockImplementation((path, options) => path === '/api/admin/staff' && options?.method === 'POST'
      ? Promise.reject(new Error('An account with that email already exists')) : fallback(path, options))
    const user = userEvent.setup()
    show()
    await screen.findByText('Eli Park')
    await enterNewStaff(user)
    await user.click(screen.getByRole('button', { name: 'Create staff account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('An account with that email already exists')
    expect(screen.getByLabelText('Email')).toHaveValue('clerk@ofs.test')
    expect(screen.getByRole('button', { name: 'Create staff account' })).toBeEnabled()
  })

  test('can retry after a staff-list error', async () => {
    const fallback = api.getMockImplementation()
    let first = true
    api.mockImplementation((path, options) => {
      if (path === '/api/admin/staff' && first) { first = false; return Promise.reject(new Error('Could not load staff')) }
      return fallback(path, options)
    })
    const user = userEvent.setup()
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load staff')
    await user.click(screen.getByRole('button', { name: 'Refresh staff' }))
    expect(await screen.findByText('Eli Park')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test.each([
    [employee, '/inventory', 'Inventory page'],
    [customer, '/', 'Home page'],
    [null, '/login', 'Login page'],
  ])('redirects accounts without manager access and never requests staff data', async (signedIn, destination, text) => {
    mockApi(signedIn)
    renderWithProviders(<Routes><Route path="/manager/staff" element={<ManagerStaff />} /><Route path={destination} element={<p>{text}</p>} /></Routes>, { route: '/manager/staff' })
    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(api).not.toHaveBeenCalledWith('/api/admin/staff')
  })
})
