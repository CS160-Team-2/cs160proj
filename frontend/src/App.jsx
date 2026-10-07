import React, { useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import Item from './pages/Item'
import Cart from './pages/Cart'
import Products from './pages/Products'
import NavigationBar from './components/NavigationBar'
import Footer from './components/Footer'

const App = () => {

  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <>
    <NavigationBar />

    <div className="pt-16 px-4 sm:px-[5vw] md:px-[7vw] lg:px-[9vw]">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/item/:itemId" element={<Item />} />
        <Route path="/products" element={<Products />} />
        <Route path="/cart" element={<Cart />} />
      </Routes>
    </div>

    <Footer />
    </>
  )
}

export default App
