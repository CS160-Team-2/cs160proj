import React, { useEffect, useState } from 'react'
import { api } from '../api'

// Formats a date and time for the history list.
const formatTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '')

// A product's stock history, newest first: when, who, how much, the new quantity and why (sales show their order number).
const StockHistory = ({ item }) => {

  const [changes, setChanges] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let current = true
    setError('')
    api(`/api/admin/inventory/${item.product_id}/changes?limit=50`)
      .then((data) => { if (current) setChanges(data.changes) })
      .catch((err) => { if (current) setError(err.message) })
    return () => { current = false }
  }, [item.product_id, item.stock])

  if (error) return <p role="alert" className="text-sm text-red-600">Could not load the history: {error}</p>
  if (!changes) return <p role="status" className="text-sm text-gray-500">Loading the history...</p>
  if (changes.length === 0) return <p className="text-sm text-gray-500">No stock changes recorded yet.</p>

  return (
    <table className="w-full text-sm text-left" aria-label={`Stock history of ${item.name}`}>
      <thead className="text-gray-500">
        <tr><th className="py-1 pr-3 font-normal">When</th><th className="py-1 pr-3 font-normal">Who</th><th className="py-1 pr-3 font-normal text-right">Change</th><th className="py-1 pr-3 font-normal text-right">New stock</th><th className="py-1 font-normal">Reason</th></tr>
      </thead>
      <tbody>
        {changes.map((change) => (
          <tr key={change.log_id} className="border-t">
            <td className="py-1 pr-3">{formatTime(change.created_at)}</td>
            <td className="py-1 pr-3">{change.changed_by || 'Customer order'}</td>
            <td className={`py-1 pr-3 text-right font-medium ${change.change_qty > 0 ? 'text-green-700' : 'text-red-700'}`}>{change.change_qty > 0 ? '+' : ''}{change.change_qty}</td>
            <td className="py-1 pr-3 text-right">{change.new_quantity}</td>
            <td className="py-1 break-words">{change.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default StockHistory
