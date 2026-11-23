// The delivery rule from the backend: free below the limit, a flat charge at the limit or above.
const DEFAULT_LIMIT = 20
const DEFAULT_CHARGE = 10

// Turns a weight in pounds into whole hundredths, so the sums below never suffer from decimal rounding.
const hundredths = (value) => Math.round(Number(value) * 100)

// Writes hundredths of a pound back as "3.50".
const pounds = (cents) => (cents / 100).toFixed(2)

// One plain sentence telling the customer how their weight affects the delivery charge, and how far they are from the line.
export const deliveryHint = (cart, currency = '$') => {
  const limit = Number(cart.free_delivery_below_lb ?? DEFAULT_LIMIT)
  const charge = Number(cart.delivery_charge ?? DEFAULT_CHARGE)
  const fee = `${currency}${charge.toFixed(2)}`
  if (!cart.items || cart.items.length === 0) {
    return `Delivery is free for orders under ${limit} lb and ${fee} for ${limit} lb or more.`
  }
  const limitCents = limit * 100
  const weightCents = hundredths(cart.total_weight_lb)
  if (weightCents < limitCents) {
    return `Delivery is free because your order is under ${limit} lb. At ${limit} lb or more it costs ${fee}, so ${pounds(limitCents - weightCents)} lb more would add the charge.`
  }
  return `Delivery costs ${fee} because your order is ${limit} lb or more. Take out ${pounds(weightCents - limitCents + 1)} lb or more and delivery is free.`
}
