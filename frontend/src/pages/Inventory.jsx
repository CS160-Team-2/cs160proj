import React, { useContext, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'

const isStaff = (user) => user && (user.role === 'employee' || user.role === 'manager')

// One form for both adding a product and editing one. Weight is always
// required, because delivery cost and vehicle capacity depend on it.
// onSubmit gets the cleaned-up values; if it throws, the message is shown
// under the form.
const ProductForm = ({ initial, withStock, submitLabel, onSubmit, onCancel }) => {

  const [form, setForm] = useState(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const change = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    const values = {
      name: form.name.trim(),
      category: form.category.trim(),
      price: form.price.trim(),
      weight: form.weight.trim(),
      description: form.description.trim(),
      stock: form.stock.trim(),
    }
    if (!values.name) {
      setError('Enter a product name.')
      return
    }
    if (values.price === '' || !(Number(values.price) >= 0)) {
      setError('Enter a price of 0 or more.')
      return
    }
    if (!(Number(values.weight) > 0)) {
      setError('Weight is required and must be greater than 0.')
      return
    }
    if (withStock && values.stock !== '' && !/^\d+$/.test(values.stock)) {
      setError('Starting stock must be a whole number.')
      return
    }
    setBusy(true)
    try {
      await onSubmit(values)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <input
        className="border px-3 py-2"
        type="text"
        placeholder="Product name"
        aria-label="Product name"
        value={form.name}
        onChange={change('name')}
      />
      <input
        className="border px-3 py-2"
        type="text"
        placeholder="Category"
        aria-label="Category"
        value={form.category}
        onChange={change('category')}
      />
      <input
        className="border px-3 py-2"
        type="number"
        step="0.01"
        min="0"
        placeholder="Price"
        aria-label="Price"
        value={form.price}
        onChange={change('price')}
      />
      <input
        className="border px-3 py-2"
        type="number"
        step="0.01"
        min="0"
        placeholder="Weight in lb (required)"
        aria-label="Weight in lb"
        value={form.weight}
        onChange={change('weight')}
      />
      {withStock && (
        <input
          className="border px-3 py-2"
          type="number"
          step="1"
          min="0"
          placeholder="Starting stock"
          aria-label="Starting stock"
          value={form.stock}
          onChange={change('stock')}
        />
      )}
      <textarea
        className="border px-3 py-2 sm:col-span-2"
        rows={2}
        placeholder="Description"
        aria-label="Description"
        value={form.description}
        onChange={change('description')}
      />
      {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" disabled={busy} className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400">{submitLabel}</button>
        <button type="button" onClick={onCancel} className="border text-sm px-6 py-2">CANCEL</button>
      </div>
    </form>
  )
}

// One product in the list: change its stock, edit it, or take it off sale.
const InventoryRow = ({ item, currency, onChanged }) => {

  const [amount, setAmount] = useState('')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(false)

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

  // Unlisting hides the product from the shop but keeps it (and every past
  // order that includes it). Listing it again puts it back on sale.
  const toggleListed = async () => {
    const url = `/api/admin/products/${item.product_id}`
    try {
      if (item.is_listed) {
        await api(url, { method: 'DELETE' })
      } else {
        await api(url, { method: 'PATCH', body: { is_listed: true } })
      }
      setMessage('')
      onChanged()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const saveEdit = async (values) => {
    if (!values.category) throw new Error('Enter a category.')
    await api(`/api/admin/products/${item.product_id}`, {
      method: 'PATCH',
      body: {
        name: values.name,
        category: values.category,
        price: values.price,
        unit_weight_lb: values.weight,
        description: values.description || null,
      },
    })
    setEditing(false)
    onChanged()
  }

  if (editing) {
    return (
      <div className="py-4 border-t border-b text-gray-700">
        <p className="font-medium mb-3">Edit product</p>
        <ProductForm
          initial={{
            name: item.name,
            category: item.category,
            price: String(item.price),
            weight: String(item.unit_weight_lb),
            description: item.description || '',
            stock: '',
          }}
          submitLabel="SAVE"
          onSubmit={saveEdit}
          onCancel={() => setEditing(false)}
        />
      </div>
    )
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
        <div className="flex gap-2 mt-2">
          <button onClick={() => setEditing(true)} className="border text-sm px-4 py-1">EDIT</button>
          <button onClick={toggleListed} className="border text-sm px-4 py-1">{item.is_listed ? 'UNLIST' : 'LIST AGAIN'}</button>
        </div>
        {message && <p className="mt-1 text-sm text-red-600">{message}</p>}
      </div>
    </div>
  )
}

// /inventory: staff see every product and can add, edit, restock and unlist
const Inventory = () => {

  const { user, currency } = useContext(StoreContext)
  const [items, setItems] = useState(null)
  const [search, setSearch] = useState('')
  const [availability, setAvailability] = useState('')
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [notice, setNotice] = useState('')

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

  const addProduct = async (values) => {
    const body = {
      name: values.name,
      price: values.price,
      unit_weight_lb: values.weight,
      initial_stock: values.stock ? parseInt(values.stock, 10) : 0,
    }
    if (values.category) body.category = values.category
    if (values.description) body.description = values.description
    await api('/api/admin/products', { method: 'POST', body })
    setAdding(false)
    setNotice(`Added ${values.name}.`)
    load()
  }

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
        <button
          onClick={() => {
            setNotice('')
            setAdding(true)
          }}
          className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400"
        >
          ADD PRODUCT
        </button>
      </div>

      {adding && (
        <div className="mb-6 border p-4 text-gray-700">
          <p className="font-medium mb-3">New product</p>
          <ProductForm
            initial={{ name: '', category: '', price: '', weight: '', description: '', stock: '' }}
            withStock
            submitLabel="ADD"
            onSubmit={addProduct}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {notice && <p className="mb-4 text-sm text-green-600">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {items && items.length === 0 && <p className="text-gray-600">No products match.</p>}
      {items && items.map((item) => (
        <InventoryRow key={item.product_id} item={item} currency={currency} onChanged={load} />
      ))}
    </div>
  )
}

export default Inventory
