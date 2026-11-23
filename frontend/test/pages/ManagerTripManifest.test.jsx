import React from 'react'
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { api } from '../../src/api'
import { renderWithProviders } from '../renderWithProviders'
import Manifest, { csvCell, manifestCsv } from '../../src/pages/ManagerTripManifest'

vi.mock('../../src/api', () => ({ api: vi.fn() }))
const trip = { trip_id: 9, vehicle: { name: 'Robot 1' }, status: 'planned', order_count: 2,
  total_weight_lb: '15.00', route_planned: true, stops: [
    { order_id: 2, order_number: 'OFS-SECOND', customer_name: 'Second Customer', address: '2 Oak St, San Jose', weight_lb: '10.00', stop_sequence: 2, est_arrival: null, delivered_at: null },
    { order_id: 1, order_number: 'OFS-FIRST', customer_name: 'Deleted customer', address: '1 Main St, San Jose', weight_lb: '5.00', stop_sequence: 1, est_arrival: '2026-11-16T10:00:00', delivered_at: null },
  ] }
let user, failure, reply
beforeEach(() => {
  vi.resetAllMocks(); user = { user_id: 3, role: 'manager' }; failure = ''; reply = structuredClone(trip)
  api.mockImplementation(async (path) => {
    if (path === '/api/auth/me') return { user }
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: { items: [], item_count: 0 } }
    if (path === '/api/admin/delivery/trips/9') { if (failure) throw new Error(failure); return { trip: reply } }
    throw new Error(path)
  })
})
afterEach(() => vi.restoreAllMocks())
function renderPage() {
  return renderWithProviders(<Routes><Route path="/manager/delivery/trips/:tripId/manifest" element={<Manifest />} /><Route path="/" element={<p>Home</p>} /><Route path="/inventory" element={<p>Inventory</p>} /><Route path="/login" element={<p>Login</p>} /></Routes>, { route: '/manager/delivery/trips/9/manifest' })
}

test('prints ordered stops, preserved addresses and a snapshot warning', async () => {
  renderPage()
  expect(await screen.findByRole('heading', { name: 'Trip #9 stop list' })).toBeInTheDocument()
  const rows = screen.getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('OFS-FIRST')
  expect(rows[1]).toHaveTextContent('OFS-SECOND')
  expect(screen.getByText('Deleted customer')).toBeInTheDocument()
  expect(screen.getByText('1 Main St, San Jose')).toBeInTheDocument()
  expect(screen.getByText(/This is a snapshot/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'OFS-FIRST' })).toHaveAttribute('href', '/manager?q=OFS-FIRST&open=1')
  const print = vi.spyOn(window, 'print').mockImplementation(() => {})
  fireEvent.click(screen.getByRole('button', { name: 'Print stop list' }))
  expect(print).toHaveBeenCalledOnce()
})

test('exports only the ordered manifest fields and neutralizes spreadsheet formulas', () => {
  const csv = manifestCsv({ ...trip, api_token_hash: 'never-export', stops: [
    { ...trip.stops[0], customer_name: '=HYPERLINK("evil")', address: '1 St, "Apt 2"' }, trip.stops[1]] })
  expect(csv.indexOf('OFS-FIRST')).toBeLessThan(csv.indexOf('OFS-SECOND'))
  expect(csv).toContain('"\'=HYPERLINK(""evil"")"')
  expect(csv).toContain('"1 St, ""Apt 2"""')
  expect(csv).not.toContain('never-export')
  expect(csv.startsWith('\uFEFF')).toBe(true)
})

test.each(['=1+1', '+SUM(1)', '-1+2', '@SUM(1)', '  =1+1', '\t=1+1', '\n=1+1'])('escapes CSV formula cell %j', (value) => {
  expect(csvCell(value).startsWith('"\'')).toBe(true)
})

test('downloads a CSV file through a temporary object URL', async () => {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:test'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  renderPage(); await screen.findByRole('heading', { name: 'Trip #9 stop list' })
  fireEvent.click(screen.getByRole('button', { name: 'Download stops CSV' }))
  expect(URL.createObjectURL).toHaveBeenCalledOnce()
  expect(click).toHaveBeenCalledOnce()
  expect(click.mock.instances[0].download).toBe('trip-9-stops.csv')
  vi.unstubAllGlobals()
})

test('explains a provisional route and empty trip', async () => {
  reply.stops = []; reply.route_planned = false; reply.order_count = 0
  renderPage()
  expect(await screen.findByText('This trip has no stops.')).toBeInTheDocument()
  expect(screen.getByText(/Stop order is provisional/)).toBeInTheDocument()
})

test('a failed lookup has a retry and cannot print stale data', async () => {
  failure = 'Trip unavailable'; renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent('Trip unavailable')
  expect(screen.queryByRole('button', { name: 'Print stop list' })).not.toBeInTheDocument()
  failure = ''; fireEvent.click(screen.getByRole('button', { name: 'Retry stop list' }))
  expect(await screen.findByRole('heading', { name: 'Trip #9 stop list' })).toBeInTheDocument()
})

test.each([['customer', 'Home'], ['employee', 'Inventory'], [null, 'Login']])('restricts manifest access for %s', async (role, page) => {
  user = role ? { user_id: 1, role } : null; renderPage()
  expect(await screen.findByText(page, { exact: true })).toBeInTheDocument()
  expect(api).not.toHaveBeenCalledWith('/api/admin/delivery/trips/9')
})
