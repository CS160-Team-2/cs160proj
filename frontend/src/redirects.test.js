import { describe, expect, test } from 'vitest'
import { isProtectedPath, loginUrl, safeNext } from './redirects'

describe('redirect helpers', () => {
  test.each(['/checkout', '/orders', '/orders/OFS-1', '/account', '/manager', '/manager/staff', '/inventory', '/delivery'])('%s needs a sign-in', (path) => {
    expect(isProtectedPath(path)).toBe(true)
  })

  test.each(['/', '/products', '/item/1', '/cart', '/login', '/track-order', '/ordersx', '/accounting'])('%s is public', (path) => {
    expect(isProtectedPath(path)).toBe(false)
  })

  test.each([
    ['/checkout', '/checkout'],
    ['/orders/OFS-1', '/orders/OFS-1'],
    ['//evil.example', '/'],
    ['https://evil.example', '/'],
    ['/\\evil.example', '/'],
    ['javascript:alert(1)', '/'],
    ['', '/'],
    [null, '/'],
  ])('safeNext(%s) is %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })

  test('loginUrl encodes the path and can flag an expired session', () => {
    expect(loginUrl('/orders/OFS-1')).toBe('/login?next=%2Forders%2FOFS-1')
    expect(loginUrl('/account', true)).toBe('/login?next=%2Faccount&expired=1')
  })
})
