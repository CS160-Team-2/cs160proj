import { test, expect } from '@playwright/test'

const customer = { email: 'customer@ofs.test', password: 'customer-pass-1' }

// Keeps only the cookies a browser would still have after it was closed and reopened.
function afterBrowserRestart(state) {
  const now = Date.now() / 1000
  return { ...state, cookies: state.cookies.filter((cookie) => cookie.expires > now) }
}

// Signs in through the form, ticking or unticking Remember me, and returns the browser state.
async function signInThroughTheForm(browser, remember) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/login')
  const box = page.getByRole('checkbox', { name: /Remember me/ })
  await expect(box).toBeChecked()
  if (!remember) await box.uncheck()
  await page.getByPlaceholder('Email').fill(customer.email)
  await page.getByPlaceholder('Password').fill(customer.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/$/)
  const state = await context.storageState()
  await context.close()
  return state
}

test('with Remember me ticked the customer is still signed in after the browser restarts', async ({ browser }) => {
  const state = await signInThroughTheForm(browser, true)
  const context = await browser.newContext({ storageState: afterBrowserRestart(state) })
  const page = await context.newPage()
  await page.goto('/account')
  await expect(page.getByRole('button', { name: 'SAVE DETAILS' })).toBeVisible()
  await expect(page).toHaveURL(/\/account$/)
  await context.close()
})

test('with Remember me unticked the sign-in is gone after the browser restarts', async ({ browser }) => {
  const state = await signInThroughTheForm(browser, false)
  const context = await browser.newContext({ storageState: afterBrowserRestart(state) })
  const page = await context.newPage()
  await page.goto('/account')
  await expect(page).toHaveURL(/\/login/)
  await context.close()
})

test('the products page finds a product by its number as well as its name', async ({ page }) => {
  await page.goto('/products')
  await page.getByLabel('Search products').fill('#2')
  await expect(page.locator('a[href="/item/2"]').first()).toBeVisible()
  await expect(page.locator('a[href="/item/1"]')).toHaveCount(0)
  await page.getByLabel('Search products').fill('apple')
  await expect(page.locator('a[href="/item/1"]').first()).toBeVisible()
})

test('product cards and product pages show the product number under the name', async ({ page }) => {
  await page.goto('/products')
  await expect(page.locator('a[href="/item/1"]').first().getByText('Product number: 1')).toBeVisible()
  await page.goto('/item/1')
  await expect(page.getByRole('heading', { level: 1 }).locator('xpath=following-sibling::p[1]')).toHaveText('Product number: 1')
})
