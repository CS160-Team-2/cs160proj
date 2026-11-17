import { test, expect } from '@playwright/test'

test.describe('navigation bar, footer and hero', () => {

  test('top bar has Track and Orders instead of About and Contact', async ({ page }) => {
    await page.goto('/')
    const bar = page.locator('div.fixed')
    await expect(bar.getByRole('link', { name: 'TRACK' })).toBeVisible()
    await expect(bar.getByRole('link', { name: 'ORDERS' })).toBeVisible()
    await expect(bar.getByText('ABOUT')).toHaveCount(0)
    await expect(bar.getByText('CONTACT')).toHaveCount(0)

    await bar.getByRole('link', { name: 'TRACK' }).click()
    await expect(page).toHaveURL(/\/track-order$/)
  })

  test('a signed-out visitor clicking Orders stays on an empty orders page, apart from Track', async ({ page }) => {
    await page.goto('/')
    await page.locator('div.fixed').getByRole('link', { name: 'ORDERS' }).click()
    await expect(page).toHaveURL(/\/orders$/)
    await expect(page.getByText('You have not placed any orders yet.')).toBeVisible()
    await expect(page.getByPlaceholder(/Order number/)).toHaveCount(0)
    await page.reload()
    await expect(page).toHaveURL(/\/orders$/)
    await expect(page.getByText('You have not placed any orders yet.')).toBeVisible()
  })

  test('the new logo is in the top bar, the footer and the browser tab icon', async ({ page }) => {
    await page.goto('/products')
    await expect(page.locator('div.fixed img[alt="OFS"]')).toBeVisible()
    await expect(page.locator('footer img[alt="OFS"]')).toBeVisible()
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/favicon.png')
    expect((await page.request.get('/favicon.png')).status()).toBe(200)
    const logo = page.locator('div.fixed img[alt="OFS"]')
    await expect(logo).toBeVisible()
    expect(await logo.evaluate((img) => img.naturalWidth)).toBeGreaterThan(300)
    // The logo file has a transparent background (no white box around the letters).
    const corner = await logo.evaluate((img) => {
      const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight
      const g = c.getContext('2d'); g.drawImage(img, 0, 0)
      return g.getImageData(2, 2, 1, 1).data[3]
    })
    expect(corner).toBe(0)
  })

  test('signed-out account menu offers only Sign in', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Account menu' }).click()
    await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Profile' })).toHaveCount(0)
  })

  test('footer shows About OFS, contact details and the copyright on every page', async ({ page }) => {
    for (const path of ['/', '/products']) {
      await page.goto(path)
      const footer = page.locator('footer')
      await expect(footer.getByRole('heading', { name: 'ABOUT' })).toBeVisible()
      await expect(footer.getByRole('heading', { name: 'CONTACT' })).toBeVisible()
      await expect(footer.getByText('hello@ofs-organic.example')).toBeVisible()
      await expect(footer.getByText('Copyright 2026 OFS - All Rights Reserved.')).toBeVisible()
    }
  })

  test('hero shows the mission with no logo in the box', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Fresh organic groceries, delivered to your door/ })).toBeVisible()
    await expect(page.getByText('OUR MISSION')).toHaveCount(0)
    await expect(page.locator('div.relative img[alt="OFS"]')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: /Fresh organic groceries/ }).locator('..')).toHaveClass(/bg-white\/70/)
  })
})
