import { test, expect } from '@playwright/test'

const customer = { email: 'customer@ofs.test', password: 'customer-pass-1' }

// Signs in through the sign-in page as the seeded customer.
async function signIn(page, next = '/') {
  await page.goto(`/login?next=${encodeURIComponent(next)}`)
  await page.getByPlaceholder('Email').fill(customer.email)
  await page.getByPlaceholder('Password').fill(customer.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test('an address the site does not have shows the 404 page, and its links work', async ({ page }) => {
  await page.goto('/no/such/page')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await page.getByRole('link', { name: 'BROWSE PRODUCTS' }).click()
  await expect(page).toHaveURL(/\/products$/)
  await page.goto('/no/such/page')
  await page.getByRole('link', { name: 'GO TO HOME' }).click()
  await expect(page).toHaveURL(/\/$/)
})

test('a product that does not exist says so instead of showing a blank page', async ({ page }) => {
  await page.goto('/item/999999')
  await expect(page.getByRole('heading', { name: 'We could not find that product' })).toBeVisible()
})

test('a signed-out visitor sent to a customer page is taken to sign in and back again', async ({ page }) => {
  await page.goto('/account')
  await expect(page).toHaveURL(/\/login\?next=%2Faccount/)
  await page.getByPlaceholder('Email').fill(customer.email)
  await page.getByPlaceholder('Password').fill(customer.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/account$/)
})

test('a sign-in link cannot send the customer to another website', async ({ page }) => {
  await signIn(page, '//example.com/phish')
  await expect(page).toHaveURL(/localhost:5173\/$/)
})

test('an order number that is not on the account shows a clear message and a way back', async ({ page }) => {
  await signIn(page)
  await expect(page).toHaveURL(/\/$/)
  await page.goto('/orders/OFS-DOES-NOT-EXIST')
  await expect(page.getByRole('heading', { name: 'We could not find that order' })).toBeVisible()
  await page.getByRole('link', { name: 'SEE ALL MY ORDERS' }).click()
  await expect(page).toHaveURL(/\/orders$/)
})

test('when the sign-in ends on the account page the customer is sent to sign in with a notice', async ({ page, context }) => {
  await signIn(page, '/account')
  await expect(page).toHaveURL(/\/account$/)
  await expect(page.getByText('SAVE DETAILS')).toBeVisible()

  await context.clearCookies()
  await page.getByRole('button', { name: 'SAVE DETAILS' }).click()

  await expect(page).toHaveURL(/\/login\?next=(%2F|\/)account/)
  await expect(page.getByRole('status')).toContainText('Your session ended')
})
