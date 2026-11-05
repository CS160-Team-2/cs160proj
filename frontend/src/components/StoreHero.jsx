import React from 'react'
import heroImage from '../assets/hero_image.jpeg'
import logo from '../assets/ofs_logo_transparent.png'

const StoreHero = () => {
  return (
    <div className="relative overflow-hidden -mx-4 sm:-mx-[5vw] md:-mx-[7vw] lg:-mx-[9vw]">
      <img className="w-full aspect-[4/3] sm:aspect-[16/9] max-h-[75vh] object-cover" src={heroImage} alt="" />
      <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-white via-white/70 to-transparent pointer-events-none"></div>
      <img
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[62%] sm:w-[44%] max-w-[640px] h-auto pointer-events-none drop-shadow-[0_6px_18px_rgba(0,0,0,0.35)]"
        src={logo}
        alt="OFS"
      />
    </div>
  )
}

export default StoreHero
