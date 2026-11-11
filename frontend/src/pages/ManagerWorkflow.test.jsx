import React from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { api } from '../api'
import { renderWithProviders } from '../test/renderWithProviders'
import ManagerProblems from './ManagerProblems'
import ManagerVehicles from './ManagerVehicles'
import SimulationRecovery from '../components/SimulationRecovery'

vi.mock('../api', () => ({ api: vi.fn() }))
const manager = { user_id: 3, full_name: 'Maya Chen', role: 'manager' }
const problem = (extra = {}) => ({ problem_id: 'payment-1', kind: 'declined',
  occurred_at: '2026-11-10T12:00:00', time_label: 'Payment recorded', order_number: null,
  order_id: null, transaction_id: 1, amount: '12.00', gateway_ref: 'decline-reference',
  card_last4: '0002', reason: 'Card declined', ...extra })
const robot = (extra = {}) => ({ vehicle_id: 1, name: 'Robot 1', max_orders: 10,
  max_weight_lb: '200.00', status: 'available', current_trip_id: null, ...extra })
let state

beforeEach(() => {
  vi.resetAllMocks()
  state = { user: manager, problems: [problem()], vehicles: [robot()], problemError: '', vehicleError: '', saveError: '', total: 1 }
  api.mockImplementation(async (path, options = {}) => {
    if (path === '/api/auth/me') return { user: state.user }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: { items: [], item_count: 0 } }
    if (path.startsWith('/api/admin/problems?')) {
      if (state.problemError) throw new Error(state.problemError)
      const params = new URLSearchParams(path.split('?')[1])
      const page = Number(params.get('page')), size = Number(params.get('per_page'))
      return { problems: state.problems, pagination: { page, per_page: size, total: state.total, total_pages: Math.max(1, Math.ceil(state.total / size)) } }
    }
    if (path === '/api/admin/delivery/vehicles' && !options.method) {
      if (state.vehicleError) throw new Error(state.vehicleError)
      return { vehicles: state.vehicles }
    }
    if (path.startsWith('/api/admin/delivery/vehicles') && options.method) {
      if (state.saveError) throw new Error(state.saveError)
      const vehicle = { ...robot(), ...options.body }
      state.vehicles = [vehicle]
      return { vehicle }
    }
    if (path.includes('/simulation/stops/')) {
      if (state.saveError) throw new Error(state.saveError)
      return { trip: {} }
    }
    throw new Error(`Unexpected request ${path}`)
  })
})
afterEach(() => vi.useRealTimers())

describe('ManagerProblems', () => {
  test('shows a declined checkout without an order and safely renders the recorded reason', async () => {
    state.problems = [problem({ reason: '<script>unsafe()</script>' })]
    const { container } = renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByText('No order created for this payment attempt.')).toBeInTheDocument()
    expect(screen.getByText('Transaction #1 · $12.00')).toBeInTheDocument()
    expect(screen.getByText(/decline-reference.*0002/)).toBeInTheDocument()
    expect(screen.getByText('<script>unsafe()</script>')).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
  })

  test('links associated orders and labels current scheduling timestamps honestly', async () => {
    state.problems = [problem({ kind: 'unscheduled', order_id: 2, order_number: 'OFS-ABC',
      problem_id: 'schedule-2', time_label: 'Order placed', transaction_id: null,
      reason: 'Too heavy for vehicle' })]
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByRole('link', { name: 'View order OFS-ABC' })).toHaveAttribute('href', '/manager?q=OFS-ABC')
    expect(screen.getByRole('link', { name: 'Open delivery board' })).toHaveAttribute('href', '/manager/delivery')
    expect(screen.getByText(/^Order placed:/)).toBeInTheDocument()
    expect(screen.getByText(/Scheduling problems disappear when resolved/)).toBeInTheDocument()
  })

  test('shows recorded refunds without adding a refund action', async () => {
    state.problems = [problem({ kind: 'refunded', reason: 'Refund recorded' })]
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByRole('heading', { name: 'Recorded refund' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /refund/i })).not.toBeInTheDocument()
  })

  test('explains an empty result', async () => {
    state.problems = []; state.total = 0
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByText('No problems match these filters.')).toBeInTheDocument()
  })

  test('an initial fetch error can be retried', async () => {
    state.problemError = 'Database unavailable'
    const user = userEvent.setup()
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
    state.problemError = ''
    await user.click(screen.getByRole('button', { name: 'Retry problems' }))
    expect(await screen.findByText('Card declined')).toBeInTheDocument()
  })

  test('keeps old results visible when a refresh fails', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    await screen.findByText('Card declined')
    state.problemError = 'Connection lost'
    await user.click(screen.getByRole('button', { name: 'Refresh problems' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Showing the last successful results.')
    expect(screen.getByText('Card declined')).toBeInTheDocument()
  })

  test('pages, applies filters, resets to page one and polls the requested page', async () => {
    const user = userEvent.setup()
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    state.total = 60
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    await screen.findByText('Card declined')
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/admin/problems?page=2&per_page=25'))
    await user.selectOptions(screen.getByLabelText('Problem type'), 'declined')
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-11-01' } })
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-11-10' } })
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    const path = '/api/admin/problems?page=1&per_page=25&kind=declined&from=2026-11-01&to=2026-11-10'
    await waitFor(() => expect(api).toHaveBeenCalledWith(path))
    await act(async () => vi.advanceTimersByTime(15000))
    expect(api.mock.calls.filter(([url]) => url === path)).toHaveLength(2)
    await user.selectOptions(screen.getByLabelText('Rows per page'), '10')
    await waitFor(() => expect(api).toHaveBeenCalledWith(path.replace('per_page=25', 'per_page=10')))
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByLabelText('Problem type')).toHaveValue('')
    expect(screen.getByLabelText('From date')).toHaveValue('')
  })

  test('reversed dates do not generate an API request', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    await screen.findByText('Card declined')
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-11-11' } })
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-11-10' } })
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(screen.getByRole('alert')).toHaveTextContent('From date must be on or before To date.')
    expect(api.mock.calls.filter(([url]) => url.startsWith('/api/admin/problems?'))).toHaveLength(1)
  })

  test('an older filtered reply cannot replace newer problems', async () => {
    const user = userEvent.setup()
    let resolveOld
    let resolveNew
    const fallback = api.getMockImplementation()
    const oldRequest = new Promise((resolve) => { resolveOld = resolve })
    const newRequest = new Promise((resolve) => { resolveNew = resolve })
    api.mockImplementation((path, ...args) => {
      if (path.includes('kind=declined')) return oldRequest
      if (path.includes('kind=refunded')) return newRequest
      return fallback(path, ...args)
    })
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    await screen.findByText('Card declined')
    await user.selectOptions(screen.getByLabelText('Problem type'), 'declined')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await user.selectOptions(screen.getByLabelText('Problem type'), 'refunded')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await act(async () => resolveNew({ problems: [problem({ reason: 'Newest response' })] }))
    expect(screen.getByText('Newest response')).toBeInTheDocument()
    await act(async () => resolveOld({ problems: [problem({ reason: 'Outdated response' })] }))
    expect(screen.queryByText('Outdated response')).not.toBeInTheDocument()
  })

  test('highlights an orphan charge requiring gateway review without a refund button', async () => {
    state.problems = [problem({ kind: 'payment_review', reason: 'Automatic refund failed' })]
    renderWithProviders(<ManagerProblems />, { route: '/manager/problems' })
    expect(await screen.findByRole('heading', { name: 'Payment needs review' })).toBeInTheDocument()
    expect(screen.getByText(/Check the payment gateway/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /refund/i })).not.toBeInTheDocument()
  })
})

describe('ManagerVehicles', () => {
  test('lists limits, availability and current trip, blocking edits for active vehicles', async () => {
    state.vehicles = [robot(), robot({ vehicle_id: 2, name: 'Robot 2', status: 'on_trip', current_trip_id: 8 })]
    renderWithProviders(<ManagerVehicles />, { route: '/manager/vehicles' })
    expect(await screen.findByRole('heading', { name: 'Robot 1' })).toBeInTheDocument()
    expect(screen.getAllByText('Maximum orders: 10 · Maximum weight: 200.00 lb')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Edit Robot 1' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Edit Robot 2' })).toBeDisabled()
    expect(screen.getByText(/Current trip: #8/)).toBeInTheDocument()
  })

  test('creates a simulated vehicle with both capacity limits', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerVehicles />, { route: '/manager/vehicles' })
    await screen.findByRole('heading', { name: 'Robot 1' })
    await user.click(screen.getByRole('button', { name: 'Add simulated vehicle' }))
    await user.type(screen.getByLabelText('Vehicle name'), 'Robot 3')
    fireEvent.change(screen.getByLabelText('Maximum orders'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Maximum weight (lb)'), { target: { value: '120.50' } })
    await user.click(screen.getByRole('button', { name: 'Create vehicle' }))
    await screen.findByText('Created Robot 3.')
    expect(api).toHaveBeenCalledWith('/api/admin/delivery/vehicles', { method: 'POST', body: { name: 'Robot 3', max_orders: 5, max_weight_lb: '120.50', status: 'available' } })
    expect(screen.queryByLabelText('Vehicle name')).not.toBeInTheDocument()
  })

  test('edits a free vehicle and moves it into maintenance', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ManagerVehicles />, { route: '/manager/vehicles' })
    await user.click(await screen.findByRole('button', { name: 'Edit Robot 1' }))
    await user.selectOptions(screen.getByLabelText('Availability'), 'maintenance')
    await user.click(screen.getByRole('button', { name: 'Save vehicle changes' }))
    expect(await screen.findByText('Status: Maintenance')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/delivery/vehicles/1', { method: 'PATCH', body: { name: 'Robot 1', max_orders: 10, max_weight_lb: '200.00', status: 'maintenance' } })
  })

  test('server conflict preserves the edit form and can be cancelled', async () => {
    const user = userEvent.setup()
    state.saveError = 'Finish the planned trip first'
    renderWithProviders(<ManagerVehicles />, { route: '/manager/vehicles' })
    await user.click(await screen.findByRole('button', { name: 'Edit Robot 1' }))
    await user.click(screen.getByRole('button', { name: 'Save vehicle changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Finish the planned trip first')
    expect(screen.getByLabelText('Vehicle name')).toHaveValue('Robot 1')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Vehicle name')).not.toBeInTheDocument()
  })

  test('empty and initial-error states are usable', async () => {
    state.vehicleError = 'Fleet unavailable'
    const user = userEvent.setup()
    renderWithProviders(<ManagerVehicles />, { route: '/manager/vehicles' })
    expect(await screen.findByRole('alert')).toHaveTextContent('Fleet unavailable')
    state.vehicleError = ''; state.vehicles = []
    await user.click(screen.getByRole('button', { name: 'Retry vehicles' }))
    expect(await screen.findByText('No vehicles have been added.')).toBeInTheDocument()
  })
})

describe('SimulationRecovery', () => {
  const trip = { trip_id: 9, status: 'out_for_delivery', vehicle_mode: 'simulated', stops: [
    { order_id: 5, order_number: 'OFS-DONE', delivered_at: '2026-11-10T10:00:00' },
    { order_id: 6, order_number: 'OFS-WAIT', delivered_at: null },
  ] }

  test('requires confirmation, targets one specific pending stop and supports cancellation', async () => {
    const user = userEvent.setup()
    const changed = vi.fn()
    render(<SimulationRecovery trip={trip} onChanged={changed} />)
    expect(screen.queryByRole('button', { name: 'Demo: complete OFS-DONE' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Demo: complete OFS-WAIT' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Your manager account and the time')
    await user.click(screen.getByRole('button', { name: 'Cancel demo completion' }))
    expect(api).not.toHaveBeenCalledWith(expect.stringContaining('/simulation/stops/'), expect.anything())
    await user.click(screen.getByRole('button', { name: 'Demo: complete OFS-WAIT' }))
    await user.click(screen.getByRole('button', { name: 'Confirm demo completion' }))
    expect(await screen.findByText('Demo delivery recorded for OFS-WAIT.')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith('/api/admin/delivery/trips/9/simulation/stops/6/complete', { method: 'POST', body: { confirmed: true } })
    expect(changed).toHaveBeenCalledOnce()
  })

  test.each([{ status: 'planned' }, { status: 'completed' }, { vehicle_mode: 'hardware' }])('is hidden for nonrecoverable trips %j', (changes) => {
    render(<SimulationRecovery trip={{ ...trip, ...changes }} onChanged={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Demo: complete/ })).not.toBeInTheDocument()
  })

  test('a failed completion keeps the dialog and does not claim success', async () => {
    state.saveError = 'Completion failed'
    const user = userEvent.setup()
    const changed = vi.fn()
    render(<SimulationRecovery trip={trip} onChanged={changed} />)
    await user.click(screen.getByRole('button', { name: 'Demo: complete OFS-WAIT' }))
    await user.click(screen.getByRole('button', { name: 'Confirm demo completion' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Completion failed')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(changed).not.toHaveBeenCalled()
  })
})

describe.each([['Problems', ManagerProblems, '/manager/problems'], ['Vehicles', ManagerVehicles, '/manager/vehicles']])('%s access', (_, Page, path) => {
  test.each([['customer', '/'], ['employee', '/inventory'], [null, '/login']])('redirects %s without requesting manager data', async (role, target) => {
    state.user = role ? { user_id: 1, role } : null
    renderWithProviders(<Routes><Route path={path} element={<Page />} /><Route path={target} element={<p>Allowed destination</p>} /></Routes>, { route: path })
    expect(await screen.findByText('Allowed destination')).toBeInTheDocument()
    expect(api.mock.calls.some(([url]) => url.startsWith('/api/admin/'))).toBe(false)
  })
})
