import { test, expect } from '@playwright/test'

const API = 'http://localhost:5001'
const APPLES = 'Organic Apples, 3 lb bag'

// Signs in as the demo employee through the login form.
async function signInAsEmployee(page) {
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill('employee@ofs.test')
  await page.getByPlaceholder('Password').fill('employee-pass-1')
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

// Reads the apples' stock straight from the shop API.
async function appleStock(page) {
  return (await (await page.request.get(`${API}/api/products/1`)).json()).product.stock
}

test('E1: the employee menu has Customer orders, a read-only list with status chips', async ({ page }) => {
  await signInAsEmployee(page)
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('link', { name: 'Customer orders', exact: true }).click()

  await expect(page).toHaveURL(/\/staff\/orders$/)
  await expect(page.getByRole('button', { name: /^All \(\d+\)$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Awaiting delivery \(\d+\)$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^(mark ready for delivery|dispatch|confirm delivered)/i })).toHaveCount(0)
  await page.getByRole('button', { name: /^Delivered \(\d+\)$/ }).click()
  await expect(page.getByRole('button', { name: /^Delivered \(\d+\)$/ })).toHaveAttribute('aria-pressed', 'true')
})

test('E1: a signed-out visitor is sent to sign in, and a customer to their own orders', async ({ page }) => {
  await page.goto('/staff/orders')
  await expect(page).toHaveURL(/\/login/)

  await page.getByPlaceholder('Email').fill('customer@ofs.test')
  await page.getByPlaceholder('Password').fill('customer-pass-1')
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).not.toHaveURL(/\/login/)
  await page.goto('/staff/orders')
  await expect(page).toHaveURL(/\/orders$/)
})

test('E4: the category filter narrows the inventory to one category', async ({ page }) => {
  await signInAsEmployee(page)
  await page.goto('/inventory')
  await expect(page.getByText(APPLES, { exact: true })).toBeVisible()

  await page.getByLabel('Filter by category').selectOption('Dairy & Eggs')

  await expect(page.getByText('Organic Whole Milk, 1 gallon')).toBeVisible()
  await expect(page.getByText(APPLES, { exact: true })).toHaveCount(0)
  await page.getByLabel('Filter by category').selectOption('')
  await expect(page.getByText(APPLES, { exact: true })).toBeVisible()
})

test('E2: a stock change needs a reason, and the reason is recorded', async ({ page }) => {
  await signInAsEmployee(page)
  await page.goto('/inventory')
  const before = await appleStock(page)
  const box = page.getByLabel(`Change stock of ${APPLES}`)
  const update = page.getByRole('button', { name: `Update stock of ${APPLES}` })

  try {
    await box.fill('3')
    await update.click()
    await expect(page.getByText('Choose a reason for the change.')).toBeVisible()
    expect(await appleStock(page)).toBe(before)

    await page.getByLabel(`Reason for changing stock of ${APPLES}`).selectOption('Other')
    await update.click()
    await expect(page.getByText('Write a few words for the reason.')).toBeVisible()
    await page.getByLabel(`Other reason for changing stock of ${APPLES}`).fill('browser test')
    await update.click()
    await expect(box).toHaveValue('')
    expect(await appleStock(page)).toBe(before + 3)

    const log = await (await page.request.get(`${API}/api/admin/inventory/1/changes`)).json()
    expect(log.changes[0].reason).toBe('Other: browser test')
  } finally {
    if ((await appleStock(page)) !== before) {
      await box.fill(String(before - (await appleStock(page))))
      await page.getByLabel(`Reason for changing stock of ${APPLES}`).selectOption('Count correction')
      await update.click()
      await expect(box).toHaveValue('')
    }
  }
  expect(await appleStock(page)).toBe(before)
})

test('E3: the low-stock level can be changed, flags the product, and is put back', async ({ page }) => {
  await signInAsEmployee(page)
  await page.goto('/inventory')
  await page.getByPlaceholder('Search products').fill('Organic Apples')
  const level = page.getByLabel(`Low-stock level of ${APPLES}`, { exact: true })
  const original = await level.inputValue()
  const flags = page.getByText('LOW', { exact: true })
  await expect(flags).toHaveCount(0)

  try {
    await level.fill('9999')
    await page.getByRole('button', { name: `Save low-stock level of ${APPLES}` }).click()
    await expect(flags).toHaveCount(1)
    await level.fill('-1')
    await page.getByRole('button', { name: `Save low-stock level of ${APPLES}` }).click()
    await expect(page.getByText('Enter a whole number, 0 or more.')).toBeVisible()
  } finally {
    await level.fill(original)
    const saved = page.waitForResponse((r) => r.url().includes('/api/admin/inventory/1') && r.request().method() === 'PATCH')
    await page.getByRole('button', { name: `Save low-stock level of ${APPLES}` }).click()
    await saved
  }
  await expect(flags).toHaveCount(0)
  await expect(level).toHaveValue(original)
})

test('E5 and E6: the description shows in the list and the history shows who changed the stock and why', async ({ page }) => {
  await signInAsEmployee(page)
  await page.goto('/inventory')
  await expect(page.getByText('Crisp, sweet organic apples, perfect for snacking or baking.')).toBeVisible()

  const box = page.getByLabel(`Change stock of ${APPLES}`)
  await box.fill('2')
  await page.getByLabel(`Reason for changing stock of ${APPLES}`).selectOption('Delivery received')
  await page.getByRole('button', { name: `Update stock of ${APPLES}` }).click()
  await expect(box).toHaveValue('')
  await page.getByRole('button', { name: `History of ${APPLES}` }).click()

  const table = page.getByRole('table', { name: `Stock history of ${APPLES}` })
  await expect(table.locator('tbody tr').first()).toContainText('Eli Park')
  await expect(table.locator('tbody tr').first()).toContainText('+2')
  await expect(table.locator('tbody tr').first()).toContainText('Delivery received')

  await box.fill('-2')
  await page.getByLabel(`Reason for changing stock of ${APPLES}`).selectOption('Count correction')
  await page.getByRole('button', { name: `Update stock of ${APPLES}` }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Count correction')       // the open history refreshes by itself
})

test('ET14: when the sign-in ends while the employee works, they are sent to sign in with a notice and return to the console', async ({ page, context }) => {
  await signInAsEmployee(page)
  await page.goto('/inventory')
  await expect(page.getByText(APPLES, { exact: true })).toBeVisible()
  await context.clearCookies()

  await page.getByLabel(`Change stock of ${APPLES}`).fill('1')
  await page.getByLabel(`Reason for changing stock of ${APPLES}`).selectOption('Count correction')
  await page.getByRole('button', { name: `Update stock of ${APPLES}` }).click()

  await expect(page).toHaveURL(/\/login\?next=%2Finventory/)
  await expect(page.getByRole('status')).toContainText('Your session ended')

  await page.getByPlaceholder('Email').fill('employee@ofs.test')
  await page.getByPlaceholder('Password').fill('employee-pass-1')
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).toHaveURL(/\/inventory$/)
})

test('ET13: signed-out visitors and customers cannot open the staff pages', async ({ page }) => {
  for (const path of ['/inventory', '/delivery', '/staff/orders']) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByText(APPLES, { exact: true })).toHaveCount(0)
  }
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill('customer@ofs.test')
  await page.getByPlaceholder('Password').fill('customer-pass-1')
  await page.getByRole('button', { name: /SIGN IN/i }).click()
  await expect(page).not.toHaveURL(/\/login/)
  for (const path of ['/inventory', '/delivery', '/staff/orders', '/manager']) {
    await page.goto(path)
    await expect(page.getByText(APPLES, { exact: true })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: /INVENTORY|DELIVERY TRACKING|CUSTOMER ORDERS/ })).toHaveCount(0)
  }
})
