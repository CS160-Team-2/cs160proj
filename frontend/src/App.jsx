import React, { useContext, useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import Item from './pages/Item'
import Cart from './pages/Cart'
import Products from './pages/Products'
import Login from './pages/Login'
import Checkout from './pages/Checkout'
import { OrderDetail, OrderHistory } from './pages/Orders'
import NavigationBar from './components/NavigationBar'
import Footer from './components/Footer'
import { StoreContext } from './context/StoreContext'

const App = () => {

  const { pathname } = useLocation()
  const { productsError } = useContext(StoreContext)

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <>
    <NavigationBar />

    <div className="pt-16 px-4 sm:px-[5vw] md:px-[7vw] lg:px-[9vw]">
      {productsError && (
        <p className="mt-4 p-3 bg-red-50 text-red-700 text-sm" role="alert">{productsError}</p>
      )}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/item/:itemId" element={<Item />} />
        <Route path="/products" element={<Products />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/login" element={<Login />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/orders" element={<OrderHistory />} />
        <Route path="/orders/:orderNumber" element={<OrderDetail />} />
      </Routes>
    </div>

    <Footer />
    </>
  )
}

export default App
