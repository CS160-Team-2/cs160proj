import { test, expect } from '@playwright/test'

const DAY_SECONDS = 24 * 60 * 60
const APPLES = '/item/1'
const cartCount = (page) => page.locator('a[href="/cart"] p')

// Puts a guest on an item page, adds two bags to the cart, and waits for the confirmation.
async function addTwoApples(page) {
  await page.goto(APPLES)
  await page.getByLabel('Quantity').fill('2')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await expect(page.getByText('Added 2 to your cart.')).toBeVisible()
  await expect(cartCount(page)).toHaveText('2')
}

// Keeps only the cookies a browser would still have after it was closed and reopened.
function afterBrowserRestart(state) {
  const now = Date.now() / 1000
  return { ...state, cookies: state.cookies.filter((cookie) => cookie.expires > now) }
}

test('a guest keeps the cart after the browser is closed and reopened', async ({ browser }) => {
  const firstVisit = await browser.newContext()
  await addTwoApples(await firstVisit.newPage())

  const state = await firstVisit.storageState()
  const session = state.cookies.find((cookie) => cookie.name === 'session')
  const daysLeft = (session.expires - Date.now() / 1000) / DAY_SECONDS
  expect(daysLeft).toBeGreaterThan(13)
  expect(daysLeft).toBeLessThanOrEqual(14.1)
  await firstVisit.close()

  const secondVisit = await browser.newContext({ storageState: afterBrowserRestart(state) })
  const page = await secondVisit.newPage()
  await page.goto('/')
  await expect(cartCount(page)).toHaveText('2')

  await page.goto('/cart')
  await expect(page.getByText('Organic Apples, 3 lb bag')).toBeVisible()
  await expect(page.locator('input[type="number"]')).toHaveValue('2')
  await secondVisit.close()
})

test('refreshing the page keeps the guest cart', async ({ page }) => {
  await addTwoApples(page)

  await page.reload()

  await expect(cartCount(page)).toHaveText('2')
})

test('a staff sign-in still ends with the browser', async ({ browser }) => {
  const context = await browser.newContext()
  const response = await context.request.post('http://localhost:5001/api/auth/login', {
    data: { email: 'manager@ofs.test', password: 'manager-pass-1' },
  })
  expect(response.ok()).toBeTruthy()

  const state = await context.storageState()
  const session = state.cookies.find((cookie) => cookie.name === 'session')
  expect(afterBrowserRestart(state).cookies).not.toContainEqual(session)
  await context.close()
})
