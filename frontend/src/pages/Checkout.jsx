import React, { useContext, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'

// The payment gateway is the backend's test fake for now, so instead of a
// card form the customer picks a test card. A real gateway would replace
// this with its own card field, which hands the page a token like these.
const testCards = [
  { token: 'tok_visa', label: 'Test Visa ending 4242 (approved)' },
  { token: 'tok_mastercard', label: 'Test Mastercard ending 4444 (approved)' },
  { token: 'tok_declined', label: 'Test card that is declined' },
]

const emptyAddress = { street: '', city: '', state: 'CA', zip_code: '' }

const Checkout = () => {

  const { user, currency, cart, reloadCart, reloadProducts } = useContext(StoreContext)
  const navigate = useNavigate()

  const [addresses, setAddresses] = useState([])
  const [addressId, setAddressId] = useState(null)
  const [showNewAddress, setShowNewAddress] = useState(false)
  const [newAddress, setNewAddress] = useState(emptyAddress)
  const [addressError, setAddressError] = useState('')

  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState('')
  const [cardToken, setCardToken] = useState(testCards[0].token)
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')

  // One key per visit to this page. A double-click or a retry after a
  // declined card sends the same key, so the backend never charges twice.
  const checkoutKey = useRef(crypto.randomUUID())

  const isCustomer = user && user.role === 'customer'

  useEffect(() => {
    if (!isCustomer) return
    api('/api/users/me/addresses').then((data) => {
      setAddresses(data.addresses)
      if (data.addresses.length > 0) setAddressId(data.addresses[0].address_id)
      else setShowNewAddress(true)
    })
  }, [isCustomer])

  // Ask the backend for the final breakdown, with tax, whenever the
  // address or the cart changes. It checks stock again and changes nothing.
  useEffect(() => {
    if (!addressId || cart.items.length === 0) {
      setPreview(null)
      return
    }
    api('/api/checkout/preview', { method: 'POST', body: { address_id: addressId } })
      .then((data) => {
        setPreview(data)
        setPreviewError('')
      })
      .catch((err) => {
        setPreview(null)
        setPreviewError(err.message)
      })
  }, [addressId, cart])

  if (user === undefined) return null
  if (!user) return <Navigate to="/login?next=/checkout" replace />
  if (!isCustomer) return <p className="pt-14 text-center text-gray-600">Staff accounts cannot place orders.</p>

  if (cart.items.length === 0 && !placing) {
    return (
      <div className="border-t-2 pt-14 text-center text-gray-600">
        <p>Your cart is empty.</p>
        <Link to="/products" className="inline-block bg-green-600 text-white mt-6 px-8 py-3 text-sm">CONTINUE SHOPPING</Link>
      </div>
    )
  }

  const saveAddress = async (event) => {
    event.preventDefault()
    setAddressError('')
    try {
      const data = await api('/api/users/me/addresses', { method: 'POST', body: newAddress })
      setAddresses([...addresses, data.address])
      setAddressId(data.address.address_id)
      setShowNewAddress(false)
      setNewAddress(emptyAddress)
    } catch (err) {
      setAddressError(err.message)
    }
  }

  const placeOrder = async () => {
    setOrderError('')
    setPlacing(true)
    try {
      const data = await api('/api/orders', {
        method: 'POST',
        body: { address_id: addressId, payment_token: cardToken, idempotency_key: checkoutKey.current },
      })
      await Promise.all([reloadCart(), reloadProducts()])
      navigate(`/orders/${data.order.order_number}`, { state: { justPlaced: true } })
    } catch (err) {
      // Declined or out of stock: the cart is unchanged, so they can retry.
      setOrderError(err.message)
      setPlacing(false)
    }
  }

  const field = (name, placeholder, extra = {}) => (
    <input
      className="border border-gray-300 px-3 py-2 w-full"
      placeholder={placeholder}
      value={newAddress[name]}
      onChange={(e) => setNewAddress({ ...newAddress, [name]: e.target.value })}
      required
      {...extra}
    />
  )

  return (
    <div className="flex flex-col lg:flex-row justify-between gap-10 pt-10 border-t-2">

      {/* Delivery address and payment */}
      <div className="flex flex-col gap-6 w-full lg:max-w-[480px]">
        <div className="text-xl sm:text-2xl">
          <TextContent text1={'DELIVERY'} text2={'ADDRESS'} />
        </div>

        {addresses.map((address) => (
          <label key={address.address_id} className={`flex gap-3 border px-4 py-3 cursor-pointer ${addressId === address.address_id ? 'border-green-600' : 'border-gray-300'}`}>
            <input
              type="radio"
              name="address"
              className="accent-green-600"
              checked={addressId === address.address_id}
              onChange={() => setAddressId(address.address_id)}
            />
            <span className="text-sm">{address.street}, {address.city}, {address.state} {address.zip_code}</span>
          </label>
        ))}

        {showNewAddress ? (
          <form onSubmit={saveAddress} className="flex flex-col gap-3">
            {field('street', 'Street address', { autoComplete: 'street-address' })}
            <div className="flex gap-3">
              {field('city', 'City', { autoComplete: 'address-level2' })}
              {field('state', 'State', { autoComplete: 'address-level1', maxLength: 50 })}
              {field('zip_code', 'ZIP', { autoComplete: 'postal-code', inputMode: 'numeric' })}
            </div>
            {addressError && <p className="text-sm text-red-600" role="alert">{addressError}</p>}
            <div className="flex gap-3">
              <button type="submit" className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400">Save address</button>
              {addresses.length > 0 && (
                <button type="button" onClick={() => setShowNewAddress(false)} className="text-sm text-gray-600 underline">Cancel</button>
              )}
            </div>
          </form>
        ) : (
          <button onClick={() => setShowNewAddress(true)} className="self-start text-sm text-green-600 underline">+ Add a new address</button>
        )}

        <div className="text-xl sm:text-2xl mt-4">
          <TextContent text1={'PAYMENT'} text2={'METHOD'} />
        </div>
        <select value={cardToken} onChange={(e) => setCardToken(e.target.value)} className="border border-gray-300 px-3 py-2 text-sm">
          {testCards.map((card) => <option key={card.token} value={card.token}>{card.label}</option>)}
        </select>
        <p className="text-xs text-gray-500 -mt-4">Test mode: no real card is charged.</p>
      </div>

      {/* Order summary */}
      <div className="w-full lg:max-w-[450px]">
        <div className="text-2xl mb-3">
          <p className="font-medium">ORDER SUMMARY</p>
        </div>

        {previewError && <p className="mb-3 text-sm text-red-600" role="alert">{previewError} <Link to="/cart" className="underline">Review your cart</Link></p>}

        <div className="flex flex-col gap-2 text-sm">
          {cart.items.map((item) => (
            <div key={item.product_id} className="flex justify-between text-gray-600">
              <p>{item.quantity} x {item.name}</p>
              <p>{currency}{item.line_total}</p>
            </div>
          ))}
          <hr />
          <Row label="Subtotal" value={`${currency}${(preview || cart).subtotal}`} />
          <Row label="Total weight" value={`${(preview || cart).total_weight_lb} lb`} />
          <Row label="Delivery fee" value={(preview || cart).delivery_fee === '0.00' ? 'Free' : `${currency}${(preview || cart).delivery_fee}`} />
          <Row label="Tax" value={preview ? `${currency}${preview.tax}` : 'Choose an address'} />
          <hr />
          <div className="flex justify-between text-base">
            <b>Total</b>
            <b>{preview ? `${currency}${preview.grand_total}` : '...'}</b>
          </div>
        </div>

        {orderError && <p className="mt-4 text-sm text-red-600" role="alert">{orderError}</p>}

        <button
          onClick={placeOrder}
          disabled={!preview || placing}
          className="w-full bg-green-600 text-white text-sm mt-8 px-8 py-3 active:bg-green-400 disabled:opacity-50"
        >
          {placing ? 'PLACING ORDER...' : 'PLACE ORDER'}
        </button>
      </div>
    </div>
  )
}

const Row = ({ label, value }) => (
  <div className="flex justify-between">
    <p>{label}</p>
    <p>{value}</p>
  </div>
)

export default Checkout
