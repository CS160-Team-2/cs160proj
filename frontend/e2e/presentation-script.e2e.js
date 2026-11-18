import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Walks the read-only parts of the final presentation script (Anna, Bob, Emily) in a real browser.
// Nothing here places an order or applies a manifest; those steps are covered by E2E_ALLOW_ORDERS tests and backend tests.
const sample = (name) => path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'examples', 'delivery-manifests', name)

// Signs in through the login form and waits for the sign-in to finish.
async function signIn(page, email, password) {
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

test.describe('Anna, the guest customer', () => {
  test('searches apples, filters by Fruits, and sees the weight and delivery fee in the cart', async ({ page }) => {
    await page.goto('/')
    await page.locator('div.fixed').getByRole('link', { name: 'PRODUCTS' }).click()
    await page.getByLabel('Search products').fill('apples')
    await expect(page.getByText('Organic Apples, 3 lb bag').first()).toBeVisible()
    await page.getByLabel('Fruits').check()
    await page.getByRole('button', { name: 'Apply Filters' }).click()
    await expect(page.getByText('Organic Apples, 3 lb bag').first()).toBeVisible()

    await page.goto('/item/1')
    await expect(page.getByText(/lb/).first()).toBeVisible()
    await page.getByRole('button', { name: 'ADD TO CART' }).click()
    await page.goto('/cart')
    await expect(page.getByText('Total Weight').locator('xpath=following-sibling::p')).toHaveText('3.00 lb')
    await expect(page.getByText('Free', { exact: true })).toBeVisible()
  })

  test('the Track page asks for an order number and email', async ({ page }) => {
    await page.goto('/track-order')
    await expect(page.getByPlaceholder(/Order number/)).toBeVisible()
    await expect(page.getByPlaceholder('Email')).toBeVisible()
  })

  test('sign in offers a way to create an account', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: /Create an account/i }).click()
    await expect(page.getByPlaceholder('Full name')).toBeVisible()
  })
})

test.describe('Bob, the employee', () => {
  test('sees only staff pages and filters stock', async ({ page }) => {
    await signIn(page, 'employee@ofs.test', 'employee-pass-1')
    await page.getByRole('button', { name: 'Account menu' }).click()
    await expect(page.getByRole('link', { name: 'Inventory' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Delivery tracking', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Manager dashboard' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Profile' })).toHaveCount(0)

    await page.goto('/inventory')
    await page.locator('select').filter({ hasText: 'Low stock' }).selectOption('out_of_stock')
    await expect(page.getByText('Delivery manifest file')).toHaveCount(0)
  })

  test('Delivery tracking shows the vehicles, the waiting orders and the trips, with no dispatch controls', async ({ page }) => {
    await signIn(page, 'employee@ofs.test', 'employee-pass-1')
    await page.getByRole('button', { name: 'Account menu' }).click()
    await page.getByRole('link', { name: 'Delivery tracking', exact: true }).click()

    await expect(page).toHaveURL(/\/delivery$/)
    const vehicles = page.getByRole('list', { name: 'Delivery vehicles' })
    await expect(vehicles).toContainText('Robot 1')
    await expect(vehicles).toContainText('Robot 2')
    await expect(vehicles).toContainText('Up to 10 orders and 200.00 lb')
    await expect(page.getByText(/No orders are waiting|Waiting \d+ min/).first()).toBeVisible()
    await expect(page.getByText('Planned trips')).toBeVisible()
    await expect(page.getByRole('button', { name: /dispatch|create trip/i })).toHaveCount(0)
  })

  test('cannot open the manager pages', async ({ page }) => {
    await signIn(page, 'employee@ofs.test', 'employee-pass-1')
    await page.goto('/manager')
    await expect(page.getByRole('heading', { name: /ORDERS/i })).toHaveCount(0)
  })
})

test.describe('Emily, the manager', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, 'manager@ofs.test', 'manager-pass-1')
  })

  test('the dashboard opens after sign in and the menu lists manager pages', async ({ page }) => {
    await expect(page).toHaveURL(/\/manager/)
    await page.getByRole('button', { name: 'Account menu' }).click()
    await expect(page.getByRole('link', { name: 'Staff accounts' })).toBeVisible()
  })

  test('a good delivery manifest previews peaches and raspberries without saving anything', async ({ page }) => {
    await page.goto('/inventory')
    await page.getByLabel('Delivery manifest file').setInputFiles(sample('delivery-good.csv'))
    await expect(page.getByRole('cell', { name: 'Organic Peaches, 2 lb' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'Organic Raspberries, 1 lb' })).toBeVisible()
    await page.getByRole('button', { name: 'CANCEL MANIFEST' }).click()
  })

  test('a manifest with mistakes lists every problem by line and cannot be applied', async ({ page }) => {
    await page.goto('/inventory')
    await page.getByLabel('Delivery manifest file').setInputFiles(sample('delivery-with-problems.csv'))
    await expect(page.getByText(/No product named "Organic Strawbery 1 lb"/)).toBeVisible()
    await expect(page.getByText(/quantity must be a whole number/i).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'APPLY MANIFEST' })).toHaveCount(0)
  })

  test('Delivery, Staff, Problems and Vehicles pages open', async ({ page }) => {
    for (const route of ['/manager/delivery', '/manager/staff', '/manager/problems', '/manager/vehicles']) {
      await page.goto(route)
      await expect(page).toHaveURL(new RegExp(`${route}$`))
      await expect(page.getByText('Page not found')).toHaveCount(0)
    }
  })
})
