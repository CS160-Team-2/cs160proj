import { test, expect } from '@playwright/test'

// C8: the cart tells the customer where the $10 delivery charge starts.
test('the cart explains the delivery rule as the weight crosses 20 lb', async ({ page }) => {
  await page.goto('/item/1')                                         // apples, 3 lb each
  await page.getByLabel('Quantity').fill('6')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await page.goto('/cart')
  await expect(page.getByTestId('delivery-hint')).toContainText('Delivery is free because your order is under 20 lb')
  await expect(page.getByTestId('delivery-hint')).toContainText('2.00 lb more would add the charge')
  await expect(page.getByText('Free', { exact: true })).toBeVisible()

  await page.locator('input[type="number"]').fill('7')
  await page.locator('input[type="number"]').blur()
  await expect(page.getByTestId('delivery-hint')).toContainText('Delivery costs $10.00 because your order is 20 lb or more')
  await expect(page.getByTestId('delivery-hint')).toContainText('Take out 1.01 lb or more')
  await expect(page.getByText('$10.00', { exact: true }).first()).toBeVisible()
})
