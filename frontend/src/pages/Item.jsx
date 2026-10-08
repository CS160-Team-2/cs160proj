import React, { useContext, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import RelatedItems from '../components/RelatedItems'

const Item = () => {

  const { itemId } = useParams()
  const { products, currency, shoppingCartItems, addToCart } = useContext(StoreContext)

  const [quantity, setQuantity] = useState('1')
  const [message, setMessage] = useState({ text: '', error: false })

  useEffect(() => {
    setQuantity('1')
    setMessage({ text: '', error: false })
  }, [itemId])

  const itemData = products.find((item) => String(item.product_id) === itemId)

  const handleAddToCart = async () => {
    const amount = Number(quantity)
    if (quantity.trim() === '' || !Number.isInteger(amount) || amount < 1) {
      setMessage({ text: 'Please enter a quantity of at least 1.', error: true })
      return
    }

    const inCart = shoppingCartItems[itemData.product_id] || 0
    const remaining = itemData.stock - inCart
    if (remaining <= 0) {
      setMessage({ text: `All ${itemData.stock} available are already in your cart.`, error: true })
      return
    }
    if (amount > remaining) {
      setMessage({ text: `Only ${remaining} more available. Please lower the quantity.`, error: true })
      return
    }

    // The backend has the final say on stock and explains any refusal.
    const result = await addToCart(itemData.product_id, amount)
    setMessage(result.ok
      ? { text: `Added ${amount} to your cart.`, error: false }
      : { text: result.message, error: true })
  }

  return itemData ? (
    <div className="border-t-2 pt-10 transition-opacity ease-in duration-500 opacity-100">
      <div className="flex gap-12 sm:gap-12 flex-col sm:flex-row">
        <div className="w-full sm:w-1/2">
          <img className="w-full aspect-square object-cover" src={itemData.image} alt={itemData.name} />
        </div>

        <div className="flex-1">
          <h1 className="font-medium text-2xl mt-2">
            {itemData.name}
          </h1>
          <p className="mt-5 text-3xl font-bold">{currency}{itemData.price}</p>
          <p className="mt-2 text-sm text-gray-500">{itemData.unit_weight_lb} lb</p>
          <p className="mt-5 text-gray-600 md:w-4/5">{itemData.description}</p>

          {itemData.available ? (
            <>
            <div className="mt-6">
              <label htmlFor="quantity" className="block text-sm font-medium text-gray-700">Quantity</label>
              <input
                id="quantity"
                className="border border-gray-300 mt-2 px-3 py-2 w-24"
                type="number"
                min={1}
                step={1}
                value={quantity}
                onChange={(e) => {
                  setQuantity(e.target.value)
                  setMessage({ text: '', error: false })
                }}
              />
              {message.text && (
                <p className={`mt-2 text-sm ${message.error ? 'text-red-600' : 'text-green-600'}`}>{message.text}</p>
              )}
            </div>
            <button className="bg-green-600 text-white mt-6 px-8 py-3 text-sm active:bg-green-400" onClick={handleAddToCart}>ADD TO CART</button>
            </>
          ) : (
            <p className="mt-8 font-medium text-red-600">Currently unavailable</p>
          )}

          <hr className="mt-8 sm:w-4/5" />
          <div className="text-sm text-gray-500 mt-5 flex flex-col gap-1">
              <p>100% organic product.</p>
              <p>Free delivery on orders under 20 lb.</p>
          </div>
        </div>
      </div>

      <RelatedItems id={itemData.product_id} category={itemData.category} />
    </div>
  ) : <div className="opacity-0"></div>
}

export default Item
