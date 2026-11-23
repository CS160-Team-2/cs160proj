import { test, expect } from '@playwright/test'

test('choosing PayPal shows only PayPal\'s own button, not Pay Later or a card button', async ({ page }) => {
  await page.goto('/item/1')
  await page.getByRole('button', { name: 'ADD TO CART' }).click()
  await expect(page.getByText('Added 1 to your cart.')).toBeVisible()
  await page.goto('/checkout')
  await expect(page.getByText('Pay with card')).toBeVisible()
  const paypalRadio = page.getByRole('radio', { name: /PayPal/ })
  test.skip((await paypalRadio.count()) === 0, 'PayPal is not set up (no sandbox keys in backend/.env)')

  const frame = page.frameLocator('iframe[title*="PayPal" i], iframe[name*="paypal" i]').first()
  let shown = false
  // PayPal's sandbox sometimes aborts the button frame, so remount it a few times before giving up.
  for (let attempt = 1; attempt <= 4 && !shown; attempt++) {
    await paypalRadio.click()
    try {
      await frame.locator('[data-funding-source="paypal"]').waitFor({ state: 'visible', timeout: 12000 })
      shown = true
    } catch {
      await page.getByRole('radio', { name: /Credit or debit card/ }).click()
    }
  }
  test.skip(!shown, "PayPal's sandbox did not serve its button after 4 tries (their service, not ours)")
  await expect(frame.locator('[data-funding-source="paylater"], [data-funding-source="card"], [data-funding-source="credit"]')).toHaveCount(0)
  await expect(page.getByPlaceholder('Card number')).toHaveCount(0)
})
