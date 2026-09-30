import React, { useContext } from 'react'
import { useParams } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import RelatedItems from '../components/RelatedItems'

const Item = () => {

  const { itemId } = useParams()
  const { products, currency, addToCart } = useContext(StoreContext)

  const itemData = products.find((item) => String(item.product_id) === itemId)

  return itemData ? (
    <div className="border-t-2 pt-10 transition-opacity ease-in duration-500 opacity-100">
      <div className="flex gap-12 sm:gap-12 flex-col sm:flex-row">
        <div className="w-full sm:w-1/2">
          <img className="w-full h-auto" src={itemData.image} alt={itemData.name} />
        </div>

        <div className="flex-1">
          <h1 className="font-medium text-2xl mt-2">
            {itemData.name}
          </h1>
          <p className="mt-5 text-3xl font-bold">{currency}{itemData.price}</p>
          <p className="mt-2 text-sm text-gray-500">{itemData.unit_weight_lb} lb</p>
          <p className="mt-5 text-gray-600 md:w-4/5">{itemData.description}</p>

          {itemData.stock > 0 ? (
            <button className="bg-green-600 text-white mt-8 px-8 py-3 text-sm active:bg-green-400" onClick={() => addToCart(itemData.product_id)}>ADD TO CART</button>
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
