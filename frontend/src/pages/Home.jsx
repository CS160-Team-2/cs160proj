import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import StoreHero from '../components/StoreHero'
import FeaturedProducts from '../components/FeaturedProducts'
import MostSold from '../components/MostSold'

const Home = () => {
  const { state } = useLocation()

  return (
    <div>
      {state?.accountDeleted && (
        <p className="mt-4 p-3 bg-green-50 border border-green-600 text-green-700 text-sm" role="status">Your account has been deleted. We are sorry to see you go.</p>
      )}
      <StoreHero />
      <FeaturedProducts />
      <MostSold />
      <div className="text-center">
        <Link to="/products" className="inline-block bg-green-600 text-white px-8 py-3 text-sm active:bg-green-400">VIEW ALL PRODUCTS</Link>
      </div>
    </div>
  )
}

export default Home
