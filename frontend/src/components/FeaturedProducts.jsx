import React, { useContext } from 'react'
import { StoreContext } from '../context/StoreContext'
import TextContent from './TextContent'
import StoreItem from './StoreItem'

const featuredIds = [4, 14, 15, 20, 37]

const FeaturedProducts = () => {

    const { products } = useContext(StoreContext)

    const items = featuredIds
        .map((id) => products.find((item) => item.product_id === id))
        .filter(Boolean)

  return (
    <div className="my-10">
      <div className="text-center py-8 text-3xl">
        <TextContent text1={"FEATURED"} text2={"PRODUCTS"} />
        <p className="w-3/4 m-auto text-xs sm:text-sm md:text-base text-gray-500">
            In-season picks from our organic shelves.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 gap-y-6">
        {
            items.map((item) => (
                <StoreItem key={item.product_id}
                           id={item.product_id}
                           name={item.name}
                           image={item.image}
                           price={item.price}
                           weight={item.unit_weight_lb}
                           available={item.stock > 0}
                />
            ))
        }
      </div>
    </div>
  )
}

export default FeaturedProducts
