import { test, expect } from '@playwright/test'

// Signs in through the login form as the demo employee.
async function signInAsEmployee(page) {
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill('employee@ofs.test')
  await page.getByPlaceholder('Password').fill('employee-pass-1')
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

// Changes the stock of the apples in the inventory console by the given amount.
async function changeAppleStock(page, delta) {
  await page.goto('/inventory')
  const box = page.getByLabel('Change stock of Organic Apples, 3 lb bag')
  await box.fill(String(delta))
  await box.locator('xpath=following-sibling::button[1]').click()
  await expect(box).toHaveValue('')
}

test('stock added in the inventory console shows on the shop without reloading the site', async ({ page }) => {
  await signInAsEmployee(page)
  const before = (await (await page.request.get('http://localhost:5001/api/products/1')).json()).product.stock

  try {
    await changeAppleStock(page, 10)
    // Move to the shop by clicking links only (no page reload), then open the apples.
    await page.locator('div.fixed').getByRole('link', { name: 'PRODUCTS' }).click()
    await page.getByLabel('Search products').fill('apples')
    await page.getByRole('link', { name: /Organic Apples, 3 lb bag/ }).first().click()
    await expect(page.getByText('In stock:')).toContainText(String(before + 10))
  } finally {
    await changeAppleStock(page, -10)
  }

  const after = (await (await page.request.get('http://localhost:5001/api/products/1')).json()).product.stock
  expect(after).toBe(before)
})
