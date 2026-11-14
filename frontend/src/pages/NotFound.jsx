import React from 'react'
import { Link } from 'react-router-dom'

// The page shown for any address the site does not have, with ways back into the shop.
const NotFound = () => (
  <div className="border-t-2 pt-14 pb-10 text-center text-gray-700">
    <p className="text-5xl font-light text-green-600">404</p>
    <h1 className="text-2xl mt-4">Page not found</h1>
    <p className="mt-2 text-gray-600">We could not find the page you were looking for. It may have moved, or the address may have a typo.</p>
    <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
      <Link to="/" className="bg-green-600 text-white px-8 py-3 text-sm">GO TO HOME</Link>
      <Link to="/products" className="border border-gray-800 px-8 py-3 text-sm">BROWSE PRODUCTS</Link>
    </div>
  </div>
)

export default NotFound
