import React, { useContext, useState } from 'react'
import { Link } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import CartTotal from '../components/CartTotal'
import { TrashIcon } from '../components/Icons'

const Cart = () => {

  const { currency, cart, cartItems: cartData, updateQuantity, removeFromCart } = useContext(StoreContext)
  const [message, setMessage] = useState('')

  const change = async (action) => {
    const result = await action
    setMessage(result.ok ? '' : result.message)
  }

  return (
    <div className="border-t-2 pt-14">
      <div className="text-2xl mb-3">
        <p className="font-medium">YOUR CART</p>
      </div>

      {cartData.length === 0 ? (
        <div className="py-16 text-center text-gray-600">
          <p>Your cart is empty.</p>
          <Link to="/" className="inline-block bg-green-600 text-white mt-6 px-8 py-3 text-sm active:bg-green-400">CONTINUE SHOPPING</Link>
        </div>
      ) : (
        <>
          {message && <p className="mb-3 text-sm text-red-600">{message}</p>}
          <div>
            {cartData.map((item) => (
              <div key={item.product_id} className="py-4 border-t border-b text-gray-700 grid grid-cols-[4fr_0.5fr_0.5fr] sm:grid-cols-[4fr_2fr_0.5fr] items-center gap-4">
                <div className="flex items-start gap-6">
                  <Link to={`/item/${item.product_id}`}>
                    <img className="w-16 sm:w-20 aspect-square object-cover" src={item.image} alt={item.name} />
                  </Link>
                  <div>
                    <p className="text-sm sm:text-lg font-medium">{item.name}</p>
                    <div className="flex items-center gap-5 mt-2">
                      <p>{currency}{item.price}</p>
                      <p className="text-sm text-gray-500">{item.unit_weight_lb} lb</p>
                    </div>
                    {item.problem && <p className="mt-1 text-sm text-red-600">{item.problem}</p>}
                  </div>
                </div>

                <input
                  className="border max-w-10 sm:max-w-20 px-1 sm:px-2 py-1"
                  type="number"
                  min={1}
                  max={item.stock}
                  value={item.quantity}
                  onChange={(e) => {
                    const value = Number(e.target.value)
                    if (Number.isInteger(value) && value > 0) change(updateQuantity(item.product_id, value))
                  }}
                />

                <button onClick={() => change(removeFromCart(item.product_id))} aria-label={`Remove ${item.name}`}>
                  <TrashIcon className="w-5 cursor-pointer" />
                </button>
              </div>
            ))}
          </div>

          <div className="flex justify-end my-20">
            <div className="w-full sm:w-[450px]">
              <CartTotal />
              <div className="w-full text-end">
                {cart.can_check_out ? (
                  <Link to="/checkout" className="inline-block bg-green-600 text-white text-sm my-8 px-8 py-3 active:bg-green-400">PROCEED TO CHECKOUT</Link>
                ) : (
                  <p className="my-8 text-sm text-red-600">Please fix the items marked above before checking out.</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Cart
