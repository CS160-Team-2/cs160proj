import React, { useContext } from 'react'
import { StoreContext } from '../context/StoreContext'

// Every figure comes from the backend, which uses the same rules as
// checkout, so the cart and the receipt always agree.
const CartTotal = () => {

  const { currency, cart } = useContext(StoreContext)
  const empty = cart.items.length === 0
  const freeDelivery = cart.delivery_fee === '0.00'

  return (
    <div className="w-full">
      <div className="text-2xl mb-3">
        <p className="font-medium">CART TOTALS</p>
      </div>

      <div className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <p>Subtotal</p>
          <p>{currency}{cart.subtotal}</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <p>Total Weight</p>
          <p>{cart.total_weight_lb} lb</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <p>Delivery Fee</p>
          <p>{empty ? `${currency}0.00` : freeDelivery ? 'Free' : `${currency}${cart.delivery_fee}`}</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <b>Total</b>
          <b>{currency}{cart.estimated_total}</b>
        </div>
        <p className="text-xs text-gray-500">Tax is added at checkout.</p>
      </div>
    </div>
  )
}

export default CartTotal
