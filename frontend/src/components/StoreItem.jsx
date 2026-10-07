import React, { useContext } from 'react'
import { Link } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'

const StoreItem = ({ id, name, image, price, weight, available }) => {

    const { currency } = useContext(StoreContext)

  return (
    <Link className="text-gray-700 cursor-pointer" to={`/item/${id}`}>
        <div className="overflow-hidden">
            <img className={`aspect-square object-cover hover:scale-120 transition ease-in-out ${available ? '' : 'opacity-50'}`} src={image} alt={name} />
        </div>

        <p className="pt-3 pb-1 text-sm">{name}</p>
        <p className="text-sm font-bold">{currency}{price}</p>
        <p className="text-xs text-gray-500">{weight} lb</p>
        {!available && <p className="text-xs font-medium text-red-600">Unavailable</p>}
    </Link>
  )
}

export default StoreItem
