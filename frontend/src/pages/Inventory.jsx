import React, { useContext, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'

const isStaff = (user) => user && (user.role === 'employee' || user.role === 'manager')

// One product in the list, with its own "change stock" box.
const InventoryRow = ({ item, currency, onChanged }) => {

  const [amount, setAmount] = useState('')
  const [message, setMessage] = useState('')

  const changeStock = async () => {
    const delta = parseInt(amount, 10)
    if (!delta) {
      setMessage('Enter a number such as 10 or -3.')
      return
    }
    try {
      await api(`/api/admin/inventory/${item.product_id}`, {
        method: 'PATCH',
        body: { delta, reason: delta > 0 ? 'Restock' : 'Adjustment' },
      })
      setAmount('')
      setMessage('')
      onChanged()
    } catch (err) {
      setMessage(err.message)
    }
  }

  return (
    <div className="py-4 border-t border-b text-gray-700 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
      <div>
        <p className="font-medium">{item.name}</p>
        <p className="text-sm text-gray-500">{item.category} · {currency}{item.price} · {item.unit_weight_lb} lb</p>
      </div>
      <p className="text-sm">
        In stock: <span className="font-medium">{item.stock}</span>
        {item.low_stock && <span className="ml-2 text-red-600">LOW</span>}
        {!item.is_listed && <span className="ml-2 text-gray-500">UNLISTED</span>}
      </p>
      <div>
        <div className="flex items-center gap-2">
          <input
            className="border max-w-20 px-2 py-1"
            type="number"
            placeholder="+/-"
            aria-label={`Change stock of ${item.name}`}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <button onClick={changeStock} className="bg-green-600 text-white text-sm px-4 py-2 active:bg-green-400">UPDATE</button>
        </div>
        {message && <p className="mt-1 text-sm text-red-600">{message}</p>}
      </div>
    </div>
  )
}

// /inventory: staff see every product and can change its stock
const Inventory = () => {

  const { user, currency } = useContext(StoreContext)
  const [items, setItems] = useState(null)
  const [search, setSearch] = useState('')
  const [availability, setAvailability] = useState('')
  const [error, setError] = useState('')

  const load = () => {
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (availability) params.set('availability', availability)
    api(`/api/admin/inventory?${params}`)
      .then((data) => {
        setItems(data.inventory)
        setError('')
      })
      .catch((err) => setError(err.message))
  }

  useEffect(() => {
    if (isStaff(user)) load()
  }, [user, search, availability])

  if (user === undefined) return null
  if (!isStaff(user)) return <Navigate to="/login" replace />

  return (
    <div className="border-t-2 pt-14">
      <div className="text-2xl mb-6">
        <TextContent text1={'INVENTORY'} text2={'CONSOLE'} />
      </div>

      <div className="flex flex-wrap gap-3 mb-6">
        <input
          className="border px-3 py-2"
          type="text"
          placeholder="Search products"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="border px-3 py-2" value={availability} onChange={(e) => setAvailability(e.target.value)}>
          <option value="">All products</option>
          <option value="available">Available</option>
          <option value="low_stock">Low stock</option>
          <option value="out_of_stock">Out of stock</option>
          <option value="unlisted">Unlisted</option>
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {items && items.length === 0 && <p className="text-gray-600">No products match.</p>}
      {items && items.map((item) => (
        <InventoryRow key={item.product_id} item={item} currency={currency} onChanged={load} />
      ))}
    </div>
  )
}

export default Inventory