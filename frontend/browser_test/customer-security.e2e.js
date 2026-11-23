import { test, expect } from '@playwright/test'

const API = 'http://localhost:5001'
const stamp = Date.now()

test('C10: after too many wrong passwords the sign-in page asks the customer to wait', async ({ page }) => {
  await page.goto('/login')
  const email = `nobody-${stamp}@example.test`
  for (let attempt = 1; attempt <= 8; attempt++) {
    await page.getByPlaceholder('Email').fill(email)
    await page.getByPlaceholder('Password').fill(`wrong-password-${attempt}`)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByText('Invalid email or password')).toBeVisible()
  }

  await page.getByPlaceholder('Password').fill('one-more-try-9')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByText(/Too many failed sign-in attempts for this account\. Please wait \d+ minutes? and try again\./)).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
})

test('C10: a script typed as a customer name is shown as plain text and never runs', async ({ page }) => {
  const payload = '<img src=x onerror=alert(1)>'
  let dialogs = 0
  page.on('dialog', async (dialog) => { dialogs += 1; await dialog.dismiss() })

  await page.goto('/login')
  await page.getByRole('button', { name: 'New here? Create an account' }).click()
  await page.getByPlaceholder('Full name').fill(payload)
  await page.getByPlaceholder('Email').fill(`xss-${stamp}@example.test`)
  await page.getByPlaceholder(/Password/).fill('xss-test-pass-1')
  await page.getByRole('button', { name: /create account/i }).last().click()
  await expect(page).not.toHaveURL(/\/login/)

  await page.goto('/account')
  await expect(page.getByLabel('Full name')).toHaveValue(payload)
  for (const path of ['/', '/orders', '/cart', '/checkout']) {
    await page.goto(path)
    await page.waitForTimeout(400)
  }
  expect(dialogs).toBe(0)
  expect(await page.locator('img[onerror]').count()).toBe(0)

  const removed = await page.request.delete(`${API}/api/users/me`, { data: { password: 'xss-test-pass-1' } })
  expect(removed.status()).toBe(200)
})
