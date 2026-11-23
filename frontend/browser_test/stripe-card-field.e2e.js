import { test, expect } from '@playwright/test'

// Puts a guest on the checkout page with one bag of apples in the cart.
async function openCheckoutWithACart(page) {
  await page.goto('/item/1')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await expect(page.getByText('Added 1 to your cart.')).toBeVisible()
  await page.goto('/checkout')
}

test("Stripe's own card field loads and accepts typing", async ({ page }) => {
  await openCheckoutWithACart(page)
  await expect(page.getByText('Pay with card')).toBeVisible()
  test.skip((await page.getByPlaceholder('Card number').count()) > 0, 'Stripe is not switched on (no publishable key, or the gateway is fake)')

  const cardFrame = page.frameLocator('iframe[title="Secure card payment input frame"]').first()
  const number = cardFrame.getByPlaceholder('Card number')
  await expect(number).toBeVisible({ timeout: 20000 })
  await number.fill('5555555555554444')
  await expect(number).toHaveValue('5555 5555 5555 4444')
  await expect(page.getByText(/Klarna|Bank/)).toHaveCount(0)
  // Stripe's test-mode badge and Link's Autofill button must stay hidden.
  await expect(page.locator('iframe[title*="developer tools" i]')).toHaveCount(0)
  await expect(cardFrame.getByText('Autofill')).toHaveCount(0)
})

// Fills the guest details and the card, then presses PLACE ORDER with the order calls answered locally, so nothing is saved or charged.
async function payWithCard(page, cardNumber) {
  await page.route('**/api/checkout/guest', (route) => route.fulfill({ status: 201, json: { ok: true, user: { user_id: 99, role: 'customer', is_guest: true }, address: { address_id: 99 } } }))
  let sent = null
  await page.route('**/api/orders', async (route) => {
    if (route.request().method() !== 'POST') return route.fulfill({ status: 200, json: { ok: true, orders: [] } })
    sent = route.request().postDataJSON()
    await route.fulfill({ status: 201, json: { ok: true, order: { order_number: 'OFS-E2E000' } } })
  })

  await openCheckoutWithACart(page)
  test.skip((await page.getByPlaceholder('Card number').count()) > 0, 'Stripe is not switched on (no publishable key, or the gateway is fake)')
  await page.getByPlaceholder('First name').fill('Anna')
  await page.getByPlaceholder('Last name').fill('Rivera')
  await page.getByPlaceholder('Email address').fill('anna@example.com')
  await page.getByPlaceholder('Phone number').fill('408 555 0123')
  await page.getByPlaceholder('Street address').fill('1 Washington Sq')
  await page.getByPlaceholder('City').fill('San Jose')
  await page.getByPlaceholder('ZIP').fill('95192')

  const cardFrame = page.frameLocator('iframe[title="Secure card payment input frame"]').first()
  await cardFrame.getByPlaceholder('Card number').fill(cardNumber)
  await cardFrame.getByPlaceholder('MM / YY').fill('12 / 34')
  await cardFrame.getByPlaceholder('CVC').fill('123')
  await cardFrame.getByPlaceholder('ZIP').fill('95192')
  await page.getByRole('button', { name: 'PLACE ORDER' }).click()
  await expect.poll(() => sent, { timeout: 20000 }).not.toBeNull()
  return sent
}

test('a Mastercard, not only the 4242 Visa, becomes a Stripe payment method', async ({ page }) => {
  const body = await payWithCard(page, '5555555555554444')

  expect(body.payment_token).toMatch(/^pm_/)
})

test('an American Express card also becomes a Stripe payment method', async ({ page }) => {
  const body = await payWithCard(page, '378282246310005')

  expect(body.payment_token).toMatch(/^pm_/)
})
