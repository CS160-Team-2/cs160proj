import { describe, expect, test } from 'vitest'
import { deliveryHint } from '../src/deliveryHint'

const cart = (weight, items = [{ product_id: 1 }]) => ({ items, total_weight_lb: weight, free_delivery_below_lb: '20.00', delivery_charge: '10.00' })

describe('deliveryHint', () => {
  test('an empty cart gets the plain rule', () => {
    expect(deliveryHint(cart('0.00', []))).toBe('Delivery is free for orders under 20 lb and $10.00 for 20 lb or more.')
  })

  test('under the limit it says how much more would add the charge', () => {
    expect(deliveryHint(cart('16.50'))).toBe('Delivery is free because your order is under 20 lb. At 20 lb or more it costs $10.00, so 3.50 lb more would add the charge.')
  })

  test('just under the limit, one hundredth of a pound is the margin', () => {
    expect(deliveryHint(cart('19.99'))).toContain('0.01 lb more would add the charge')
  })

  test('exactly at the limit the charge applies, as in the backend rule', () => {
    expect(deliveryHint(cart('20.00'))).toBe('Delivery costs $10.00 because your order is 20 lb or more. Take out 0.01 lb or more and delivery is free.')
  })

  test('over the limit it says how much to take out to make it free', () => {
    expect(deliveryHint(cart('22.00'))).toContain('Take out 2.01 lb or more and delivery is free.')
  })

  test('uses the limit and charge the server sends, and falls back to 20 lb and $10', () => {
    expect(deliveryHint({ ...cart('5.00'), free_delivery_below_lb: '15.00', delivery_charge: '7.50' })).toContain('under 15 lb. At 15 lb or more it costs $7.50, so 10.00 lb more')
    expect(deliveryHint({ items: [{ product_id: 1 }], total_weight_lb: '5.00' })).toContain('under 20 lb')
  })

  test('a different currency symbol is used', () => {
    expect(deliveryHint(cart('1.00'), '€')).toContain('€10.00')
  })
})
