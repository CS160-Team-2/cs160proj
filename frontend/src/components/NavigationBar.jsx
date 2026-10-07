import React, { useContext } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { HomeIcon, ProfileIcon, ShoppingCartIcon } from './Icons'

const NavigationBar = () => {

  const { getShoppingCartCount } = useContext(StoreContext)

  return (
    <div className="flex items-center justify-between px-7 py-2 font-semibold bg-green-600 fixed w-full top-0 z-50">
      <Link to="/" className="flex items-center gap-2 text-white">
        <HomeIcon className="w-8" />
        <span className="text-xl tracking-wide">OFS</span>
      </Link>

      <ul className="hidden sm:flex gap-5 text-sm text-white">
        <NavLink to="/" className="flex flex-col items-center gap-1 cursor-pointer">
          <p>HOME</p>
          <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
        </NavLink>
        <NavLink to="/products" className="flex flex-col items-center gap-1 cursor-pointer">
          <p>PRODUCTS</p>
          <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
        </NavLink>
        <li className="flex flex-col items-center gap-1 cursor-default">
          <p>ABOUT</p>
          <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
        </li>
        <li className="flex flex-col items-center gap-1 cursor-default">
          <p>CONTACT</p>
          <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
        </li>
      </ul>

      <div className="flex items-center gap-5 text-white">
        <div className="cursor-default" aria-disabled="true">
          <ProfileIcon className="w-8" />
        </div>

        <Link to="/cart" className="relative">
          <ShoppingCartIcon className="w-8" />
          <p className="absolute right-[-4px] bottom-[20px] w-4 text-center leading-4 bg-yellow-400 text-black rounded-full text-[10px]">{getShoppingCartCount()}</p>
        </Link>
      </div>
    </div>
  )
}

export default NavigationBar
