import React, { useContext } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'

export default function ManagerAccess({ children }) {
  const { user } = useContext(StoreContext)
  const { pathname } = useLocation()
  if (user === undefined) return <p role="status">Checking your account...</p>
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(pathname)}`} replace />
  if (user.role !== 'manager') return <Navigate to={user.role === 'employee' ? '/inventory' : '/'} replace />
  return children
}
