import React, { useContext, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'
import { CardIcon, LockIcon } from '../components/Icons'

const emptyCard = { name: '', number: '', expiry: '', cvc: '' }

const stripeTestTokens = {
  '4242424242424242': 'tok_visa',
  '5555555555554444': 'tok_mastercard',
  '4000000000000002': 'tok_declined',
  '4000000000009995': 'tok_insufficient',
  '4000000000000069': 'tok_expired',
}

const digitsOnly = (value) => value.replace(/\D/g, '')

const formatNumber = (value) => digitsOnly(value).slice(0, 19).replace(/(.{4})/g, '$1 ').trim()

const formatExpiry = (value) => {
  const digits = digitsOnly(value).slice(0, 4)
  return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
}

const passesLuhn = (number) => {
  let sum = 0
  for (let i = 0; i < number.length; i++) {
    let digit = Number(number[number.length - 1 - i])
    if (i % 2 === 1) {
      digit *= 2
      if (digit > 9) digit -= 9
    }
    sum += digit
  }
  return sum % 10 === 0
}

const cardError = (card) => {
  const number = digitsOnly(card.number)
  if (!card.name.trim()) return 'Enter the name on the card.'
  if (number.length < 13 || number.length > 19 || !passesLuhn(number)) return 'Enter a valid card number.'
  const match = card.expiry.match(/^(\d{2})\/(\d{2})$/)
  if (!match || Number(match[1]) < 1 || Number(match[1]) > 12) return 'Enter the expiry date as MM/YY.'
  const expires = new Date(2000 + Number(match[2]), Number(match[1]), 1)
  if (expires <= new Date()) return 'This card has expired.'
  if (!/^\d{3,4}$/.test(card.cvc)) return 'Enter the 3 or 4 digit security code.'
  return ''
}

const cardToken = (card) => {
  const number = digitsOnly(card.number)
  return stripeTestTokens[number] || `tok_card_${number.slice(-4)}`
}

const emptyAddress = { street: '', city: '', state: 'CA', zip_code: '' }
const emptyContact = { first_name: '', last_name: '', email: '', phone: '' }
const guestKey = 'ofs_guest_checkout'

const loadGuest = () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(guestKey))
    return { contact: { ...emptyContact, ...saved.contact }, address: { ...emptyAddress, ...saved.address } }
  } catch {
    return { contact: emptyContact, address: emptyAddress }
  }
}

const saveGuest = (contact, address) => {
  try {
    sessionStorage.setItem(guestKey, JSON.stringify({ contact, address }))
  } catch {
    return
  }
}

const clearGuest = () => {
  try {
    sessionStorage.removeItem(guestKey)
  } catch {
    return
  }
}

const Checkout = () => {

  const { user, currency, cart, reloadCart, reloadProducts, guestCheckout } = useContext(StoreContext)
  const navigate = useNavigate()

  const [addresses, setAddresses] = useState([])
  const [addressId, setAddressId] = useState(null)
  const [showNewAddress, setShowNewAddress] = useState(false)
  const [saved] = useState(loadGuest)
  const [contact, setContact] = useState(saved.contact)
  const [newAddress, setNewAddress] = useState(saved.address)
  const [addressError, setAddressError] = useState('')

  const [preview, setPreview] = useState(null)
  const [estimate, setEstimate] = useState(null)
  const [previewError, setPreviewError] = useState('')
  const [card, setCard] = useState(emptyCard)
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')

  // One key per visit to this page. A double-click or a retry after a
  // declined card sends the same key, so the backend never charges twice.
  const checkoutKey = useRef(crypto.randomUUID())

  const isCustomer = user && user.role === 'customer'
  const isGuest = user === null

  useEffect(() => {
    if (isGuest) saveGuest(contact, newAddress)
  }, [isGuest, contact, newAddress])

  useEffect(() => {
    if (!isGuest || cart.items.length === 0) {
      setEstimate(null)
      return
    }
    api('/api/checkout/estimate')
      .then((data) => {
        setEstimate(data)
        setPreviewError('')
      })
      .catch((err) => {
        setEstimate(null)
        setPreviewError(err.message)
      })
  }, [isGuest, cart])

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
  if (user && !isCustomer) return <p className="pt-14 text-center text-gray-600">Staff accounts cannot place orders.</p>

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

  const guestProblem = () => {
    if (!contact.first_name.trim() || !contact.last_name.trim()) return 'Enter your first and last name.'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact.email.trim())) return 'Enter a valid email address.'
    if (digitsOnly(contact.phone).length < 7) return 'Enter a valid phone number.'
    if (!newAddress.street.trim() || !newAddress.city.trim() || !newAddress.state.trim()) return 'Enter your full delivery address.'
    if (!/^\d{5}(-\d{4})?$/.test(newAddress.zip_code.trim())) return 'Enter a 5 digit ZIP code.'
    return ''
  }

  const placeOrder = async () => {
    const problem = (isGuest && guestProblem()) || cardError(card)
    if (problem) {
      setOrderError(problem)
      return
    }

    setOrderError('')
    setPlacing(true)
    try {
      let chosenAddressId = addressId
      if (isGuest) {
        const started = await guestCheckout(
          Object.fromEntries(Object.entries(contact).map(([name, value]) => [name, value.trim()])),
          Object.fromEntries(Object.entries(newAddress).map(([name, value]) => [name, value.trim()])),
        )
        chosenAddressId = started.address.address_id
      }
      const data = await api('/api/orders', {
        method: 'POST',
        body: { address_id: chosenAddressId, payment_token: cardToken(card), idempotency_key: checkoutKey.current },
      })
      clearGuest()
      await Promise.all([reloadCart(), reloadProducts()])
      navigate('/orders', { state: { justPlaced: true, orderNumber: data.order.order_number } })
    } catch (err) {
      setOrderError(err.message)
      setPlacing(false)
    }
  }

  const contactField = (name, placeholder, extra = {}) => (
    <input
      className="border border-gray-300 px-3 py-2 w-full"
      placeholder={placeholder}
      value={contact[name]}
      onChange={(e) => setContact({ ...contact, [name]: e.target.value })}
      {...extra}
    />
  )

  const totals = isGuest ? estimate : preview

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
          <TextContent text1={'CONTACT'} text2={'INFORMATION'} />
        </div>

        {isGuest ? (
          <div className="flex flex-col gap-3 -mt-2">
            <div className="flex gap-3">
              {contactField('first_name', 'First name', { autoComplete: 'given-name' })}
              {contactField('last_name', 'Last name', { autoComplete: 'family-name' })}
            </div>
            {contactField('email', 'Email address', { type: 'email', autoComplete: 'email' })}
            {contactField('phone', 'Phone number', { type: 'tel', autoComplete: 'tel', inputMode: 'tel' })}
            <p className="text-sm text-gray-600">
              Have an account? <Link to="/login?next=/checkout" className="text-green-600 underline">Sign in</Link> or create one. Your cart will be waiting right here.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-1 text-sm text-gray-600 -mt-3">
            <p>{user.full_name}</p>
            <p>{user.email}</p>
            <p>{user.phone || 'No phone number on file'}</p>
          </div>
        )}

        <div className="text-xl sm:text-2xl mt-2">
          <TextContent text1={'DELIVERY'} text2={'ADDRESS'} />
        </div>

        {isGuest && (
          <div className="flex flex-col gap-3 -mt-2">
            {field('street', 'Street address', { autoComplete: 'street-address' })}
            <div className="flex gap-3">
              {field('city', 'City', { autoComplete: 'address-level2' })}
              {field('state', 'State', { autoComplete: 'address-level1', maxLength: 50 })}
              {field('zip_code', 'ZIP', { autoComplete: 'postal-code', inputMode: 'numeric' })}
            </div>
          </div>
        )}

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

        {isGuest ? null : showNewAddress ? (
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
        <div className="flex flex-col gap-3 border border-gray-300 rounded px-4 py-4">
          <div className="flex items-center justify-between text-sm text-gray-700">
            <p className="font-medium flex items-center gap-2"><CardIcon className="w-5" /> Pay with card</p>
            <p className="flex items-center gap-1 text-xs text-gray-500"><LockIcon className="w-3.5" /> Secure payment</p>
          </div>
          <input
            className="border border-gray-300 rounded py-1.5 px-3.5 w-full"
            placeholder="Name on card"
            autoComplete="off"
            value={card.name}
            onChange={(e) => setCard({ ...card, name: e.target.value })}
          />
          <input
            className="border border-gray-300 rounded py-1.5 px-3.5 w-full"
            placeholder="Card number"
            autoComplete="off"
            inputMode="numeric"
            value={card.number}
            onChange={(e) => setCard({ ...card, number: formatNumber(e.target.value) })}
          />
          <div className="flex gap-3">
            <input
              className="border border-gray-300 rounded py-1.5 px-3.5 w-full"
              placeholder="MM/YY"
              autoComplete="off"
              inputMode="numeric"
              value={card.expiry}
              onChange={(e) => setCard({ ...card, expiry: formatExpiry(e.target.value) })}
            />
            <input
              className="border border-gray-300 rounded py-1.5 px-3.5 w-full"
              placeholder="CVC"
              autoComplete="off"
              inputMode="numeric"
              maxLength={4}
              value={card.cvc}
              onChange={(e) => setCard({ ...card, cvc: digitsOnly(e.target.value) })}
            />
          </div>
        </div>
        <p className="text-xs text-gray-500 -mt-4">Test mode: no real card is charged. Use 4242 4242 4242 4242 to be approved or 4000 0000 0000 0002 to be declined, with any future expiry and any CVC.</p>
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
          <Row label="Subtotal" value={`${currency}${(totals || cart).subtotal}`} />
          <Row label="Total weight" value={`${(totals || cart).total_weight_lb} lb`} />
          <Row label="Delivery fee" value={(totals || cart).delivery_fee === '0.00' ? 'Free' : `${currency}${(totals || cart).delivery_fee}`} />
          <Row label="Tax" value={totals ? `${currency}${totals.tax}` : 'Choose an address'} />
          <hr />
          <div className="flex justify-between text-base">
            <b>Total</b>
            <b>{totals ? `${currency}${totals.grand_total}` : '...'}</b>
          </div>
        </div>

        {orderError && <p className="mt-4 text-sm text-red-600" role="alert">{orderError}</p>}

        <button
          onClick={placeOrder}
          disabled={!totals || placing}
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
