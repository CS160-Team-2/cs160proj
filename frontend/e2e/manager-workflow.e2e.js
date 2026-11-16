import { test, expect } from '@playwright/test'

// Browser layout/navigation checks with explicit API fixtures. These do not
// log into, reset or mutate the team's application database. Real API and
// process-restart tests live in backend/test_manager_remaining.py and
// backend/test_simulator_recovery.py.
const order = { order_id: 1, order_number: 'OFS-MANAGER-QA', status: 'assigned_to_trip',
  customer_name: 'Deleted customer', customer_email: null, placed_at: '2026-11-16T10:00:00',
  item_count: 1, total_weight_lb: '199.00', grand_total: '25.00', trip_id: 1, unscheduled_reason: null }
const trip = { trip_id: 1, status: 'planned', vehicle_mode: 'simulated',
  vehicle: { vehicle_id: 1, name: 'R'.repeat(60), max_orders: 10, max_weight_lb: '200.00' },
  order_count: 1, total_weight_lb: '199.00', remaining_orders: 9, remaining_weight_lb: '1.00',
  capacity_problem: null, route_planned: true, active_provider: 'fake', route_provider_changed: false,
  route: { provider: 'fake', store: { latitude: '37.3352', longitude: '-121.8811' }, path: [[37.3352, -121.8811], [37.34, -121.89]], total_minutes: 10 },
  stops: [{ order_id: 1, order_number: order.order_number, customer_name: 'Deleted customer',
    address: '1 Historical Avenue, San Jose, CA 95113', latitude: '37.34', longitude: '-121.89',
    weight_lb: '199.00', stop_sequence: 1, est_arrival: '2026-11-16T11:00:00', delivered_at: null,
    status: 'assigned_to_trip' }], created_at: order.placed_at, started_at: null, completed_at: null,
  last_report: null, last_position: null }

async function fixtures(page, { changedProvider = false } = {}) {
  const currentTrip = { ...trip, route_provider_changed: changedProvider, active_provider: changedProvider ? 'mapbox' : 'fake' }
  await page.route('**/api/**', async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname
    const headers = { 'Access-Control-Allow-Origin': 'http://localhost:5173',
      'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS' }
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    let data
    if (path === '/api/auth/me') data = { user: { user_id: 3, full_name: 'QA Manager', role: 'manager' } }
    if (path === '/api/products') data = { products: [] }
    if (path === '/api/cart') data = { cart: { items: [], item_count: 0 } }
    if (path === '/api/admin/orders') data = { orders: [order], status_counts: { placed: 0, awaiting_delivery: 0, assigned_to_trip: 1, out_for_delivery: 0, delivered: 0 }, pagination: { page: 1, per_page: 25, total: 1, total_pages: 1 } }
    if (path === '/api/admin/orders/1') data = { order: { ...order, subtotal: '20.00', tax: '1.00', delivery_fee: '4.00',
      customer: { full_name: 'Deleted customer', email: null, phone: null },
      address: { street: '1 Historical Avenue', city: 'San Jose', state: 'CA', zip_code: '95113' },
      items: [{ product_id: 1, name: 'Preserved paid item', quantity: 1, unit_weight_lb: '199.00', line_total: '20.00' }],
      payment: { card_last4: '4242' }, history: [{ to_status: 'placed', changed_at: order.placed_at, changed_by: null }] } }
    if (path === '/api/admin/orders/1/tracking') data = { map: null, estimated_arrival: null }
    if (path === '/api/admin/orders/1/payments') data = { payments: [{ transaction_id: 1, gateway_ref: 'r'.repeat(100), status: 'approved', amount: '25.00', card_last4: '4242', failure_reason: null, created_at: order.placed_at }] }
    if (path === '/api/admin/delivery/trips') data = { trips: [currentTrip] }
    if (path === '/api/admin/delivery/trips/1') data = { trip: currentTrip }
    if (path === '/api/admin/delivery/queue') data = { orders: [{ order_id: 2, order_number: 'OFS-WAITING-ORDER', total_weight_lb: '201.00', placed_at: order.placed_at, waited_minutes: 30 }] }
    if (path === '/api/admin/delivery/exceptions') data = { orders: [] }
    if (path === '/api/admin/delivery/vehicles') data = { vehicles: [{ ...trip.vehicle, status: 'available', current_trip_id: 1 }, { ...trip.vehicle, vehicle_id: 2, status: 'available', current_trip_id: null }] }
    if (path === '/api/admin/staff') data = { staff: [{ user_id: 3, full_name: 'QA Manager', email: 'qa-manager@ofs.test', role: 'manager', is_active: true }, { user_id: 2, full_name: 'QA Employee', email: 'qa-employee@ofs.test', role: 'employee', is_active: true }] }
    if (path === '/api/admin/problems') data = { problems: [{ problem_id: 'payment-1', kind: 'declined', occurred_at: order.placed_at, time_label: 'Payment recorded', reason: 'Card declined', transaction_id: 1, amount: '25.00', card_last4: '0002', gateway_ref: 'qa-reference', order_id: null, order_number: null }], pagination: { page: 1, per_page: 25, total: 1, total_pages: 1 } }
    if (!data) return route.fulfill({ status: 404, headers, json: { ok: false, error: { code: 'QA_UNEXPECTED_REQUEST', message: path } } })
    await route.fulfill({ headers, json: { ok: true, ...data } })
  })
}

for (const [name, width, height] of [['desktop', 1440, 1000], ['tablet', 768, 1024], ['phone', 390, 844], ['small-phone', 320, 740]]) {
  test.describe(name, () => {
    test.use({ viewport: { width, height } })
    test('manager pages and expanded order have no sideways document scroll', async ({ page }) => {
      await fixtures(page)
      const pages = [
        ['/manager?q=OFS-MANAGER-QA&open=1', 'Preserved paid item'],
        ['/manager/delivery?trip=1', 'Print or export trip #1 stop list'],
        ['/manager/delivery/trips/1/manifest', 'Trip #1 stop list'],
        ['/manager/staff', 'QA Employee'], ['/manager/vehicles', 'Maximum orders:'],
        ['/manager/problems', 'Card declined'],
      ]
      for (const [path, text] of pages) {
        await page.goto(path)
        await expect(page.getByText(text, { exact: false }).first()).toBeVisible()
        const size = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
        expect(size.document, `${name}: ${path}`).toBeLessThanOrEqual(size.viewport + 1)
      }
    })
  })
}

test('M10 order and trip links work both ways and expand the matching order', async ({ page }) => {
  await fixtures(page)
  await page.goto('/manager')
  await page.getByRole('link', { name: 'Open trip #1', exact: true }).click()
  await expect(page.getByLabel('Delivery trip', { exact: true })).toHaveValue('1')
  await page.getByRole('link', { name: order.order_number, exact: true }).click()
  await expect(page.getByText('Preserved paid item', { exact: false })).toBeVisible()
  await expect(page.getByText('Deleted customer', { exact: true })).toBeVisible()
  await expect(page.getByText('1 Historical Avenue, San Jose, CA 95113', { exact: true })).toBeVisible()
})

test('M11 stop list prints without site navigation and downloads CSV', async ({ page }) => {
  await fixtures(page)
  await page.goto('/manager/delivery/trips/1/manifest')
  await expect(page.getByRole('heading', { name: 'Trip #1 stop list' })).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download stops CSV' }).click()
  expect((await downloaded).suggestedFilename()).toBe('trip-1-stops.csv')
  await page.emulateMedia({ media: 'print' })
  await expect(page.getByRole('navigation', { name: 'Manager pages' })).toBeHidden()
  await expect(page.getByRole('button', { name: 'Print stop list' })).toBeHidden()
  await expect(page.getByText('Copyright 2026 OFS - All Rights Reserved.')).toBeHidden()
  await expect(page.getByText('1 Historical Avenue, San Jose, CA 95113')).toBeVisible()
})

test('MB5 a provider-change warning blocks dispatch and offers replanning', async ({ page }) => {
  await fixtures(page, { changedProvider: true })
  await page.goto('/manager/delivery?trip=1')
  await expect(page.getByRole('alert')).toContainText('Map provider changed to Mapbox')
  await expect(page.getByRole('button', { name: 'DISPATCH', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Re-plan route', exact: true })).toBeEnabled()
})
