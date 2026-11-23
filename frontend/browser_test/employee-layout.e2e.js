import { test, expect } from '@playwright/test'

// EB4: the employee pages must not scroll sideways on a tablet or a phone.
for (const [name, width, height] of [['desktop', 1440, 900], ['tablet', 768, 1024], ['phone', 390, 844], ['small phone', 320, 700]]) {
  test.describe(name, () => {
    test.use({ viewport: { width, height } })

    test('inventory, customer orders and delivery tracking have no sideways scroll, and the history opens', async ({ page }) => {
      await page.goto('/login')
      await page.getByPlaceholder('Email').fill('employee@ofs.test')
      await page.getByPlaceholder('Password').fill('employee-pass-1')
      await page.getByRole('button', { name: /SIGN IN/i }).click()
      await expect(page).not.toHaveURL(/\/login/)

      for (const path of ['/inventory', '/staff/orders', '/delivery']) {
        await page.goto(path)
        await expect(page.locator('div.fixed')).toBeVisible()
        await page.waitForTimeout(600)
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
        expect(overflow, `${path} at ${width}px scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(0)
      }

      await page.goto('/inventory')
      await page.getByRole('button', { name: 'History of Organic Apples, 3 lb bag' }).click()
      await expect(page.getByRole('table', { name: 'Stock history of Organic Apples, 3 lb bag' })).toBeVisible()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow, `inventory with history open at ${width}px`).toBeLessThanOrEqual(0)
    })
  })
}
