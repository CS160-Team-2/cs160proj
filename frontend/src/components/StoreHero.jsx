import React from 'react'
import heroImage from '../assets/hero_image.jpeg'

// Home page hero image with the OFS mission (black-to-green lettering) centered on it.
const StoreHero = () => {
  return (
    <div className="relative overflow-hidden -mx-4 sm:-mx-[5vw] md:-mx-[7vw] lg:-mx-[9vw]">
      <img className="w-full aspect-[4/3] sm:aspect-[16/9] max-h-[75vh] object-cover" src={heroImage} alt="" />
      <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-white via-white/70 to-transparent pointer-events-none"></div>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[88%] sm:w-[62%] max-w-[760px] rounded-lg border-4 border-green-600 bg-white/70 px-5 py-6 sm:px-10 sm:py-9 text-center shadow-lg backdrop-blur-sm">
        <h1 className="bg-gradient-to-r from-black to-green-600 bg-clip-text text-transparent text-2xl sm:text-4xl lg:text-5xl font-extrabold leading-tight">
          Fresh organic groceries, delivered to your door.
        </h1>
      </div>
    </div>
  )
}

export default StoreHero
