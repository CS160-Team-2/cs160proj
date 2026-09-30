import React from 'react'
import { assets } from '../assets/assets'

const StoreHero = () => {
  return (
    <div className="flex flex-col sm:flex-row border-l border-r border-b border-green-600">
      <img className="w-full sm:w-1/2" src={assets.lettuce} alt="" />

      <div className="w-full sm:w-1/2 flex items-center justify-center py-10 sm:py-0">
        <div className="text-[#414141]">
            <div className="flex items-center gap-3">
                <p className="font-medium text-sm md:text-base">SHOP NOW AT</p>
                <p className="w-10 md:w-15 h-[2px] bg-[#414141]"></p>
            </div>
            <h1 className="text-3xl sm:py-3 lg:text-4xl leading-relaxed">
                OFS ORGANIC GROCERIES
            </h1>
        </div>
      </div>
    </div>
  )
}

export default StoreHero
