import React, { useContext } from 'react'
import { StoreContext } from '../context/StoreContext'
import TextContent from './TextContent'
import StoreItem from './StoreItem'

const AllProducts = () => {

    const { products } = useContext(StoreContext)

  return (
    <div className="my-10">
      <div className="text-center py-8 text-3xl">
        <TextContent text1={"OUR"} text2={"PRODUCTS"} />
        <p className="w-3/4 m-auto text-xs sm:text-sm md:text-base text-gray-500">
            Fresh organic fruits, vegetables and pantry essentials, delivered to your door. Orders under 20 lb ship free.
        </p>
      </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 gap-y-6">
            {
                products.map((item) => (
                    <StoreItem
                        key={item.product_id}
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

export default AllProducts
