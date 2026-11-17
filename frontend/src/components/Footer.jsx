import React from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/ofs_logo_cropped.png'

// Site footer with a short About, quick links, Contact details and the copyright line.
const Footer = () => {
  return (
    <footer className="print:hidden bg-green-600 mt-40 text-white">
      <div className="px-4 sm:px-[5vw] md:px-[7vw] lg:px-[9vw] pt-10 pb-6 grid gap-10 sm:grid-cols-[2fr_1fr_1.4fr] text-sm">
        <div id="about">
          <img src={logo} alt="OFS" className="h-14 w-auto mb-4" />
          <h2 className="font-bold mb-2">ABOUT</h2>
          <p className="max-w-md text-green-50">
            OFS is an on-demand food delivery service for organic groceries. We stock fresh, certified organic
            produce, dairy and pantry goods, and our own vehicles bring them to your door, with live tracking
            from the moment your order leaves the store.
          </p>
        </div>

        <div>
          <h2 className="font-bold mb-2">COMPANY</h2>
          <ul className="flex flex-col gap-1 text-green-50">
            <li><Link to="/" className="hover:underline">Home</Link></li>
            <li><Link to="/products" className="hover:underline">Products</Link></li>
            <li><Link to="/track-order" className="hover:underline">Track your order</Link></li>
            <li><Link to="/orders" className="hover:underline">Orders</Link></li>
          </ul>
        </div>

        <div id="contact">
          <h2 className="font-bold mb-2">CONTACT</h2>
          <ul className="flex flex-col gap-1 text-green-50">
            <li><a href="tel:+14085550142" className="hover:underline">+1 (408) 555-0142</a></li>
            <li><a href="mailto:hello@ofs-organic.example" className="hover:underline">hello@ofs-organic.example</a></li>
            <li>Open daily, 8 am to 8 pm</li>
          </ul>
        </div>
      </div>
      <p className="py-5 text-sm text-center border-t border-green-500">Copyright 2026 OFS - All Rights Reserved.</p>
    </footer>
  )
}

export default Footer
