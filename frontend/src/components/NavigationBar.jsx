import React, { useContext, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { ProfileIcon, ShoppingCartIcon } from './Icons'
import logo from '../assets/ofs_logo_cropped.png'

// Top bar: Home, Products, Track and Orders links, the account menu and the cart.
const NavigationBar = () => {

  const { getShoppingCartCount, user, signOut } = useContext(StoreContext)
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()
  const isStaff = user?.role === 'employee' || user?.role === 'manager'
  const isCustomer = user?.role === 'customer' && !user.is_guest

  // Closes the menu, signs the user out and returns to the home page.
  const handleSignOut = async () => {
    setMenuOpen(false)
    await signOut()
    navigate('/')
  }

  return (
    <div className="print:hidden flex items-center justify-between h-14 px-7 py-2 font-semibold bg-green-600 fixed w-full top-0 z-50">
      <Link to="/" className="flex items-center" aria-label="OFS home">
        <img src={logo} alt="OFS" className="h-10 w-auto" />
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
        {!isStaff && (
          <>
            <NavLink to="/track-order" className="flex flex-col items-center gap-1 cursor-pointer">
              <p>TRACK</p>
              <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
            </NavLink>
            <NavLink to="/orders" end className="flex flex-col items-center gap-1 cursor-pointer">
              <p>ORDERS</p>
              <hr className="w-2/4 border-none h-[1.5px] bg-white hidden" />
            </NavLink>
          </>
        )}
      </ul>

      <div className="flex items-center gap-5 text-white">
        <div className="relative">
          <button onClick={() => setMenuOpen(!menuOpen)} aria-label="Account menu" aria-expanded={menuOpen} className="cursor-pointer flex">
            <ProfileIcon className="w-8" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-44 bg-white text-gray-700 text-sm shadow-md flex flex-col py-2">
              {/* On a phone the top bar has no links, so the main pages live here too. */}
              {!isStaff && (
                <div className="flex flex-col sm:hidden border-b border-gray-200 mb-1 pb-1">
                  <Link to="/products" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Products</Link>
                  <Link to="/track-order" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Track</Link>
                  <Link to="/orders" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Orders</Link>
                </div>
              )}
              {user && (isCustomer || isStaff) ? (
                <>
                  {isCustomer && (
                    <Link to="/account" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Profile</Link>
                  )}
                  {user.role === 'manager' && (
                    <>
                      <Link to="/manager" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Manager dashboard</Link>
                      <Link to="/manager/staff" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Staff accounts</Link>
                    </>
                  )}
                  {isStaff && (
                    <>
                      <Link to="/inventory" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Inventory</Link>
                      <Link to="/delivery" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Delivery tracking</Link>
                    </>
                  )}
                  <button onClick={handleSignOut} className="px-4 py-2 text-left hover:bg-gray-100 cursor-pointer">Sign out</button>
                </>
              ) : (
                <Link to="/login" onClick={() => setMenuOpen(false)} className="px-4 py-2 hover:bg-gray-100">Sign in</Link>
              )}
            </div>
          )}
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
