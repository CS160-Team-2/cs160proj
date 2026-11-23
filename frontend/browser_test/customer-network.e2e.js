import { test, expect } from '@playwright/test'

// CT24: when the store cannot be reached the customer is told so, never that their cart or orders are empty.
test('the cart says it could not load, and TRY AGAIN works once the store is back', async ({ page }) => {
  await page.goto('/item/1')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await expect(page.getByText('Added 1 to your cart.')).toBeVisible()

  await page.route('**/api/cart', (route) => route.abort('connectionrefused'))
  await page.goto('/cart')
  await expect(page.getByRole('heading', { name: 'We could not load your cart' })).toBeVisible()
  await expect(page.getByText('Your cart is empty.')).toHaveCount(0)
  await page.goto('/checkout')
  await expect(page.getByRole('heading', { name: 'We could not load your cart' })).toBeVisible()

  await page.unroute('**/api/cart')
  await page.getByRole('button', { name: 'TRY AGAIN' }).click()
  await expect(page.getByRole('heading', { name: 'We could not load your cart' })).toHaveCount(0)
  await expect(page.getByText('Pay with card')).toBeVisible()
})

test('a signed-in customer is not told they have no orders while the store is out of reach', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill('customer@ofs.test')
  await page.getByPlaceholder('Password').fill('customer-pass-1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login/)

  await page.route('**/api/auth/me', (route) => route.abort('connectionrefused'))
  await page.goto('/orders')
  await expect(page.getByText('We cannot reach the store right now')).toBeVisible()
  await expect(page.getByText('You have not placed any orders yet.')).toHaveCount(0)

  await page.unroute('**/api/auth/me')
  await expect(page.getByRole('heading', { name: /ORDERS/ }).or(page.getByText('MY'))).toBeVisible({ timeout: 15000 })
})
