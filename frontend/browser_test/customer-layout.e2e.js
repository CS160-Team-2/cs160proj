import { test, expect } from '@playwright/test'

// C4, CB3, CB6, CT18: the customer pages fit a phone and a tablet, and every main page can be reached from the menu.
const PAGES = ['/', '/products', '/item/1', '/cart', '/checkout', '/login', '/track-order', '/orders', '/does-not-exist']

for (const [name, width, height] of [['tablet', 768, 1024], ['phone', 390, 844], ['small phone', 320, 700]]) {
  test.describe(name, () => {
    test.use({ viewport: { width, height } })

    test('no customer page scrolls sideways', async ({ page }) => {
      await page.goto('/item/1')
      await page.getByRole('button', { name: 'ADD TO CART' }).click()
      await expect(page.getByText('Added 1 to your cart.')).toBeVisible()
      for (const path of PAGES) {
        await page.goto(path)
        await page.waitForTimeout(500)
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
        expect(overflow, `${path} at ${width}px scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(0)
      }
    })

    test('the menu reaches Products, Track and Orders, and the logo, cart and menu icons are all on screen', async ({ page }) => {
      await page.goto('/')
      for (const label of ['Account menu', 'OFS home']) {
        const box = await page.getByRole(label === 'OFS home' ? 'link' : 'button', { name: label }).boundingBox()
        expect(box, `${label} is on screen`).not.toBeNull()
        expect(box.x + box.width).toBeLessThanOrEqual(width)
      }
      const cart = await page.locator('a[href="/cart"]').first().boundingBox()
      expect(cart.x + cart.width).toBeLessThanOrEqual(width)

      if (width < 640) {
        const bar = page.locator('div.fixed')
        await page.getByRole('button', { name: 'Account menu' }).click()
        await bar.getByRole('link', { name: 'Products', exact: true }).click()
        await expect(page).toHaveURL(/\/products$/)
        await page.getByRole('button', { name: 'Account menu' }).click()
        await bar.getByRole('link', { name: 'Track', exact: true }).click()
        await expect(page).toHaveURL(/\/track-order$/)
        await page.getByRole('button', { name: 'Account menu' }).click()
        await bar.getByRole('link', { name: 'Orders', exact: true }).click()
        await expect(page).toHaveURL(/\/orders$/)
      }
    })
  })
}
