import { test, expect } from '@playwright/test'

// C14 browser UI checks use explicit API responses. They create no orders
// and call no live mapping provider. Backend tests verify the real API.
const number = 'OFS-C14QA'
const email = 'c14-browser@example.com'
const order = {
  order_number: number, placed_at: '2026-11-16T10:00:00', status: 'placed',
  items: [{ product_id: 1, name: 'C14 preview apples', quantity: 1, line_total: '6.49' }],
  address: { street: '200 E Santa Clara St', city: 'San Jose', state: 'CA', zip_code: '95113' },
  payment: { card_last4: '4242' }, subtotal: '6.49', tax: '0.65',
  total_weight_lb: '3.00', delivery_fee: '0.00', grand_total: '7.14',
}
const tracking = {
  order_number: number, status: 'placed', estimated_arrival: null,
  steps: [
    { status: 'placed', done: true }, { status: 'awaiting_delivery', done: false },
    { status: 'assigned_to_trip', done: false }, { status: 'out_for_delivery', done: false },
    { status: 'delivered', done: false },
  ],
  map: {
    preview: true, provider: null, trip_status: null,
    store: { latitude: '37.335200', longitude: '-121.881100' },
    destination: { latitude: '37.340000', longitude: '-121.890000' },
    vehicle_mode: null, vehicle_position: null, last_report: null,
    last_updated: null, directions_url: null,
  },
}

async function fixtures(page, signedIn) {
  await page.route(/https:\/\/[^/]*mapbox\.(com|cn)\//, (route) =>
    route.fulfill({ status: 401, json: { message: 'C14 test: external maps disabled' } }))
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const headers = {
      'Access-Control-Allow-Origin': 'http://localhost:5173',
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    }
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    let data
    if (path === '/api/auth/me') data = { user: signedIn ? { user_id: 1, full_name: 'Preview Customer', role: 'customer' } : null }
    if (path === '/api/products') data = { products: [] }
    if (path === '/api/cart') data = { cart: { items: [], item_count: 0 } }
    if (path === '/api/orders/' + number) data = { order }
    if (path === '/api/orders/' + number + '/tracking') data = tracking
    if (path === '/api/orders/lookup') {
      const details = request.postDataJSON()
      if (details.order_number !== number || details.email !== email) {
        return route.fulfill({ status: 404, headers, json: {
          ok: false, error: { code: 'ORDER_NOT_FOUND', message: 'We could not find an order with that order number and email.' },
        } })
      }
      data = { order, tracking }
    }
    if (!data) return route.fulfill({ status: 404, headers, json: {
      ok: false, error: { code: 'C14_UNEXPECTED_REQUEST', message: path },
    } })
    return route.fulfill({ headers, json: { ok: true, ...data } })
  })
}

async function expectPreview(page) {
  await expect(page.getByRole('region', { name: 'Delivery map preview' })).toBeVisible()
  await expect(page.getByRole('img', { name: /^Delivery address preview (map|diagram)$/ })).toBeVisible()
  await expect(page.getByText(/Your route will appear once your order is assigned/)).toBeVisible()
  await expect(page.getByText('Blue: store · Green: your delivery address', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open route in Google Maps' })).toHaveCount(0)
  await expect(page.getByText(/Waiting for the vehicle to report/)).toHaveCount(0)
  await expect(page.locator('svg[aria-label="Delivery address preview diagram"] polyline')).toHaveCount(0)
}

test('C14 signed-in customer sees the address preview before assignment', async ({ page }) => {
  await fixtures(page, true)
  await page.goto('/orders/' + number)
  await expectPreview(page)
  await expect(page.getByText(/Delivering to 200 E Santa Clara St/)).toBeVisible()
})

test('C14 guest lookup shows a preview and removes it after a refused lookup', async ({ page }) => {
  await fixtures(page, false)
  await page.goto('/track-order')
  await page.getByPlaceholder('Order number, like OFS-AB12CD').fill(number)
  await page.getByPlaceholder('Email', { exact: true }).fill(email)
  await page.getByRole('button', { name: 'Track order', exact: true }).click()
  await expectPreview(page)
  await page.getByPlaceholder('Email', { exact: true }).fill('wrong@example.com')
  await page.getByRole('button', { name: 'Track order', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('We could not find an order')
  await expect(page.getByRole('region', { name: 'Delivery map preview' })).toHaveCount(0)
})
