import React, { useContext, useEffect } from 'react'
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
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
import Inventory from './pages/Inventory'
import TrackOrder from './pages/TrackOrder'
import Account from './pages/Account'
import { ManagerDelivery, ManagerOrders } from './pages/Manager'
import EmployeeDelivery from './pages/EmployeeDelivery'
import ManagerStaff from './pages/ManagerStaff'
import ManagerProblems from './pages/ManagerProblems'
import ManagerVehicles from './pages/ManagerVehicles'
import NotFound from './pages/NotFound'
import ErrorBoundary from './components/ErrorBoundary'
import { isProtectedPath, loginUrl } from './redirects'

const App = () => {

  const { pathname } = useLocation()
  const { productsError, sessionExpired, dismissSessionExpired } = useContext(StoreContext)
  const navigate = useNavigate()

  // When the sign-in runs out on a page that needs one, sends the customer to sign in and back again.
  useEffect(() => {
    if (sessionExpired && isProtectedPath(pathname)) navigate(loginUrl(pathname, true), { replace: true })
  }, [sessionExpired, pathname, navigate])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <>
    <NavigationBar />

    <div className="pt-14 px-4 sm:px-[5vw] md:px-[7vw] lg:px-[9vw]">
      {productsError && (
        <p className="mt-4 p-3 bg-red-50 text-red-700 text-sm" role="alert">{productsError}</p>
      )}
      {sessionExpired && !isProtectedPath(pathname) && (
        <p className="mt-4 p-3 bg-amber-50 text-amber-800 text-sm flex flex-wrap gap-3 items-center" role="alert">
          Your session ended, so you have been signed out.
          <Link to={loginUrl(pathname, true)} className="underline">Sign in again</Link>
          <button type="button" onClick={dismissSessionExpired} className="underline ml-auto">Dismiss</button>
        </p>
      )}
      <ErrorBoundary key={pathname}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/item/:itemId" element={<Item />} />
        <Route path="/products" element={<Products />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/login" element={<Login />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/orders" element={<OrderHistory />} />
        <Route path="/track-order" element={<TrackOrder />} />
        <Route path="/account" element={<Account />} />
        <Route path="/orders/:orderNumber" element={<OrderDetail />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/delivery" element={<EmployeeDelivery />} />
        <Route path="/manager" element={<ManagerOrders />} />
        <Route path="/manager/delivery" element={<ManagerDelivery />} />
        <Route path="/manager/staff" element={<ManagerStaff />} />
        <Route path="/manager/problems" element={<ManagerProblems />} />
        <Route path="/manager/vehicles" element={<ManagerVehicles />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      </ErrorBoundary>
    </div>

    <Footer />
    </>
  )
}

export default App
