import React from 'react'
import { Link } from 'react-router-dom'
import StoreHero from '../components/StoreHero'
import FeaturedProducts from '../components/FeaturedProducts'
import MostSold from '../components/MostSold'

const Home = () => {
  return (
    <div>
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
