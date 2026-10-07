import React, { useContext } from 'react'
import { StoreContext } from '../context/StoreContext'

const CartTotal = () => {

  const { currency, getCartAmount, getCartWeight, getDeliveryFee } = useContext(StoreContext)

  const subtotal = getCartAmount()
  const deliveryFee = getDeliveryFee()
  const total = subtotal === 0 ? 0 : subtotal + deliveryFee

  return (
    <div className="w-full">
      <div className="text-2xl mb-3">
        <p className="font-medium">CART TOTALS</p>
      </div>

      <div className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <p>Subtotal</p>
          <p>{currency}{subtotal.toFixed(2)}</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <p>Total Weight</p>
          <p>{getCartWeight().toFixed(2)} lb</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <p>Delivery Fee</p>
          <p>{subtotal === 0 ? `${currency}0.00` : deliveryFee === 0 ? 'Free' : `${currency}${deliveryFee.toFixed(2)}`}</p>
        </div>
        <hr />
        <div className="flex justify-between">
          <b>Total</b>
          <b>{currency}{total.toFixed(2)}</b>
        </div>
      </div>
    </div>
  )
}

export default CartTotal
