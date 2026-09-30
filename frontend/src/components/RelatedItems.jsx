import React, { useContext } from 'react'
import { StoreContext } from '../context/StoreContext'
import TextContent from './TextContent'
import StoreItem from './StoreItem'

const RelatedItems = ({ id, category }) => {

    const { products } = useContext(StoreContext)

    const relatedItems = products
        .filter((item) => item.category === category && item.product_id !== id)
        .slice(0, 5)

  if (relatedItems.length === 0) return null

  return (
    <div className="my-24">
      <div className="text-center text-3xl py-2">
        <TextContent text1={"RELATED"} text2={"ITEMS"} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 gap-y-6">
        {
            relatedItems.map((item) => (
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

export default RelatedItems
