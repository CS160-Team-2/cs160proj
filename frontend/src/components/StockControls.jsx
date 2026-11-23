import React, { useState } from 'react'
import { api } from '../api'

// The reasons an employee can give for a stock change; "Other" asks for a few words.
export const STOCK_REASONS = ['Delivery received', 'Returned to stock', 'Damaged or spoiled', 'Count correction', 'Other']

// Change a product's stock by a number, always with a reason (the audit trail records who, when and why).
export const StockChange = ({ item, onChanged }) => {

  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [other, setOther] = useState('')
  const [message, setMessage] = useState('')

  // Sends the change after checking the number and the reason.
  const changeStock = async () => {
    const delta = parseInt(amount, 10)
    if (!delta) return setMessage('Enter a number such as 10 or -3.')
    if (!reason) return setMessage('Choose a reason for the change.')
    if (reason === 'Other' && !other.trim()) return setMessage('Write a few words for the reason.')
    try {
      await api(`/api/admin/inventory/${item.product_id}`, {
        method: 'PATCH',
        body: { delta, reason: reason === 'Other' ? `Other: ${other.trim()}` : reason },
      })
      setAmount('')
      setReason('')
      setOther('')
      setMessage('')
      onChanged()
    } catch (err) {
      setMessage(err.message)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <input
          className="border max-w-20 px-2 py-1"
          type="number"
          placeholder="+/-"
          aria-label={`Change stock of ${item.name}`}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <select
          className="border px-2 py-1 text-sm min-w-0"
          aria-label={`Reason for changing stock of ${item.name}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        >
          <option value="">Reason...</option>
          {STOCK_REASONS.map((text) => <option key={text} value={text}>{text}</option>)}
        </select>
      </div>
      {reason === 'Other' && (
        <input
          className="border px-2 py-1 text-sm"
          type="text"
          maxLength={200}
          placeholder="Why?"
          aria-label={`Other reason for changing stock of ${item.name}`}
          value={other}
          onChange={(e) => setOther(e.target.value)}
        />
      )}
      <button onClick={changeStock} aria-label={`Update stock of ${item.name}`} className="self-start bg-green-600 text-white text-sm px-4 py-2 active:bg-green-400">UPDATE</button>
      {message && <p className="text-sm text-red-600" role="alert">{message}</p>}
    </div>
  )
}

// Shows the stock level at which a product counts as LOW, and lets staff change it.
export const LowStockLevel = ({ item, onChanged }) => {

  const [value, setValue] = useState(String(item.low_stock_threshold ?? ''))
  const [message, setMessage] = useState('')
  const changed = value !== String(item.low_stock_threshold ?? '')

  // Saves the new level if it is a whole number of 0 or more.
  const save = async () => {
    if (!/^\d+$/.test(value.trim())) return setMessage('Enter a whole number, 0 or more.')
    try {
      await api(`/api/admin/inventory/${item.product_id}`, { method: 'PATCH', body: { low_stock_threshold: parseInt(value, 10) } })
      setMessage('')
      onChanged()
    } catch (err) {
      setMessage(err.message)
    }
  }

  return (
    <div className="mt-1 text-xs text-gray-600">
      <label className="flex items-center gap-1">
        Low when at or below
        <input
          className="border w-14 px-1 py-0.5"
          type="number"
          min="0"
          aria-label={`Low-stock level of ${item.name}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      {changed && <button onClick={save} aria-label={`Save low-stock level of ${item.name}`} className="mt-1 border px-3 py-0.5">SAVE</button>}
      {message && <p className="text-red-600" role="alert">{message}</p>}
    </div>
  )
}
