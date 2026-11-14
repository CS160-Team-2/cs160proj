import { test, expect } from '@playwright/test'

// Tests that place real orders (and real Stripe test charges) run only when E2E_ALLOW_ORDERS=1.
const allowOrders = process.env.E2E_ALLOW_ORDERS === '1'
const stamp = Date.now()

const guest = {
  first: 'Anna',
  last: 'Tester',
  email: `e2e-${stamp}@example.test`,
  phone: '408 555 0123',
  street: '1 Washington Sq',
  city: 'San Jose',
  zip: '95192',
}

const cardFrame = (page) => page.frameLocator('iframe[title="Secure card payment input frame"]').first()
const paypalFrame = (page) => page.frameLocator('iframe[title*="PayPal" i], iframe[name*="paypal" i]').first()

// Puts a guest on the checkout page with one bag of apples in the cart.
async function openCheckoutWithACart(page) {
  await page.goto('/item/1')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await expect(page.getByText('Added 1 to your cart.')).toBeVisible()
  await page.goto('/checkout')
  await expect(page.getByText('Pay with card')).toBeVisible()
}

// Skips the test when the page shows the built-in test form instead of Stripe's field.
async function requireStripe(page) {
  test.skip((await page.getByPlaceholder('Card number').count()) > 0, 'Stripe is not switched on (no publishable key, or the gateway is fake)')
  await expect(cardFrame(page).getByPlaceholder('Card number')).toBeVisible({ timeout: 20000 })
}

// Skips the test when PayPal is not set up (no radio buttons appear).
async function requirePayPal(page) {
  test.skip((await page.getByRole('radio', { name: /PayPal/ }).count()) === 0, 'PayPal is not set up (no sandbox keys in backend/.env)')
}

// Chooses PayPal and returns its button; PayPal's sandbox sometimes aborts the button frame, so remount it a few times, then skip.
async function choosePayPal(page) {
  const button = paypalFrame(page).locator('[data-funding-source="paypal"]')
  for (let attempt = 1; attempt <= 4; attempt++) {
    await page.getByRole('radio', { name: /PayPal/ }).click()
    try {
      await button.waitFor({ state: 'visible', timeout: 12000 })
      return button
    } catch {
      await page.getByRole('radio', { name: /Credit or debit card/ }).click()
    }
  }
  test.skip(true, "PayPal's sandbox did not serve its button after 4 tries (their service, not ours)")
}

// Types the guest's contact details and address into the checkout form.
async function fillGuestDetails(page) {
  await page.getByPlaceholder('First name').fill(guest.first)
  await page.getByPlaceholder('Last name').fill(guest.last)
  await page.getByPlaceholder('Email address').fill(guest.email)
  await page.getByPlaceholder('Phone number').fill(guest.phone)
  await page.getByPlaceholder('Street address').fill(guest.street)
  await page.getByPlaceholder('City').fill(guest.city)
  await page.getByPlaceholder('ZIP').fill(guest.zip)
}

// Types a card into Stripe's field.
async function typeCard(page, number) {
  const frame = cardFrame(page)
  await frame.getByPlaceholder('Card number').fill(number)
  await frame.getByPlaceholder('MM / YY').fill('12 / 34')
  await frame.getByPlaceholder('CVC').fill('123')
  await frame.getByPlaceholder('ZIP').fill('95192')
}

test.describe('choosing how to pay', () => {

  // PayPal's frames and windows load from the internet, so give these tests more time.
  test.setTimeout(90000)

  test('card is chosen first and PayPal is a second choice that swaps the form', async ({ page }) => {
    await openCheckoutWithACart(page)
    await requirePayPal(page)
    await requireStripe(page)
    await expect(page.getByRole('radio', { name: /Credit or debit card/ })).toBeChecked()

    await choosePayPal(page)
    await expect(page.locator('iframe[title="Secure card payment input frame"]')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'PLACE ORDER' })).toHaveCount(0)

    await page.getByRole('radio', { name: /Credit or debit card/ }).click()
    await expect(cardFrame(page).getByPlaceholder('Card number')).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'PLACE ORDER' })).toBeVisible()
  })

  test('PayPal refuses to start until a guest has filled in their details', async ({ page }) => {
    await openCheckoutWithACart(page)
    await requirePayPal(page)
    const button = await choosePayPal(page)
    await button.click({ noWaitAfter: true })

    await expect(page.getByRole('alert')).toContainText('Enter your first and last name.', { timeout: 20000 })
  })

  test('PayPal creates an order on our server and opens PayPal\'s checkout window', async ({ page }) => {
    await openCheckoutWithACart(page)
    await requirePayPal(page)
    await fillGuestDetails(page)
    const button = await choosePayPal(page)

    const created = page.waitForResponse((response) => response.url().includes('/api/payments/paypal/order'), { timeout: 30000 })
    const popup = page.waitForEvent('popup', { timeout: 30000 })
    await button.click({ noWaitAfter: true })

    const response = await created
    expect(response.status()).toBe(201)
    expect((await response.json()).id).toBeTruthy()
    const paypalWindow = await popup
    await paypalWindow.waitForURL(/paypal\.com/, { timeout: 30000 })
    await paypalWindow.close()
  })
})

test.describe('paying by card (places real orders; run with E2E_ALLOW_ORDERS=1)', () => {

  test.skip(!allowOrders, 'These tests place orders and Stripe test charges. Set E2E_ALLOW_ORDERS=1 to run them.')

  for (const [label, number] of [['a Visa', '4242424242424242'], ['a Mastercard', '5555555555554444']]) {
    test(`${label} is approved, the order is placed and the cart is emptied`, async ({ page }) => {
      await openCheckoutWithACart(page)
      await requireStripe(page)
      await fillGuestDetails(page)
      await typeCard(page, number)

      await page.getByRole('button', { name: 'PLACE ORDER' }).click()

      await expect(page).toHaveURL(/\/orders$/, { timeout: 30000 })
      await expect(page.getByText(/Your order number is OFS-/)).toBeVisible()
      await expect(page.locator('a[href="/cart"] p')).toHaveText('0')
    })
  }

  for (const [label, number, reason] of [
    ['a declined card', '4000000000000002', 'Card declined'],
    ['a card with insufficient funds', '4000000000009995', 'Insufficient funds'],
  ]) {
    test(`${label} keeps the customer on checkout with a clear message and the cart unchanged`, async ({ page }) => {
      await openCheckoutWithACart(page)
      await requireStripe(page)
      await fillGuestDetails(page)
      await typeCard(page, number)

      await page.getByRole('button', { name: 'PLACE ORDER' }).click()

      await expect(page.getByRole('alert')).toContainText(`Payment declined: ${reason}`, { timeout: 30000 })
      await expect(page).toHaveURL(/\/checkout$/)
      await expect(page.locator('a[href="/cart"] p')).toHaveText('1')
    })
  }
})
