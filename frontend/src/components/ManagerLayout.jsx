import React from 'react'
import { NavLink } from 'react-router-dom'
import TextContent from './TextContent'

const ManagerLayout = ({ title, children }) => (
  <div className="border-t-2 pt-14">
    <div className="text-2xl mb-6"><TextContent text1="MANAGER" text2={title} /></div>
    <nav aria-label="Manager pages" className="flex flex-wrap gap-2 border-b border-gray-300 mb-8">
      {[
        ['/manager', 'Orders'], ['/manager/delivery', 'Delivery'],
        ['/manager/problems', 'Problems'], ['/manager/vehicles', 'Vehicles'],
        ['/manager/staff', 'Staff'], ['/inventory', 'Inventory'],
      ].map(([to, label]) => (
        <NavLink key={to} to={to} end className={({ isActive }) => `px-4 py-2 text-sm ${isActive ? 'border-b-2 border-green-600 font-medium text-green-700' : 'text-gray-600'}`}>{label}</NavLink>
      ))}
    </nav>
    {children}
  </div>
)

export default ManagerLayout
