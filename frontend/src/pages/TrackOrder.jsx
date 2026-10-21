import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import TextContent from '../components/TextContent'
import { OrderView } from './Orders'

const TrackOrder = () => {

  const [orderNumber, setOrderNumber] = useState('')
  const [email, setEmail] = useState('')
  const [looking, setLooking] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const searched = useRef(null)

  const lookUp = async (details) => {
    const data = await api('/api/orders/lookup', { method: 'POST', body: details })
    setResult({ order: data.order, tracking: data.tracking })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setLooking(true)
    const details = { order_number: orderNumber.trim().toUpperCase(), email: email.trim() }
    try {
      await lookUp(details)
      searched.current = details
    } catch (err) {
      searched.current = null
      setResult(null)
      setError(err.message)
    } finally {
      setLooking(false)
    }
  }

  useEffect(() => {
    if (!result) return
    const timer = setInterval(() => {
      if (searched.current) lookUp(searched.current).catch(() => {})
    }, 15000)
    return () => clearInterval(timer)
  }, [result !== null])

  return (
    <div className="border-t-2 pt-14 flex flex-col gap-10">
      <form onSubmit={handleSubmit} className="flex flex-col items-center w-full sm:max-w-96 m-auto gap-4 text-gray-800">
        <div className="text-3xl">
          <TextContent text1={'TRACK'} text2={'ORDER'} />
        </div>
        <p className="text-sm text-gray-600 text-center">
          Enter the order number from your confirmation and the email you used at checkout.
        </p>
        <input
          className="w-full px-3 py-2 border border-gray-800 uppercase placeholder:normal-case"
          type="text"
          placeholder="Order number, like OFS-AB12CD"
          value={orderNumber}
          onChange={(e) => setOrderNumber(e.target.value)}
          required
        />
        <input
          className="w-full px-3 py-2 border border-gray-800"
          type="email"
          placeholder="Email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        {error && <p className="w-full text-sm text-red-600" role="alert">{error}</p>}

        <button
          type="submit"
          disabled={looking}
          className="bg-green-600 text-white font-light px-8 py-2 mt-2 active:bg-green-400 disabled:opacity-60"
        >
          {looking ? 'Please wait...' : 'Track order'}
        </button>
        <p className="text-sm text-gray-600">
          Have an account? <Link to="/login?next=/orders" className="text-green-600 underline">Sign in</Link> to see all your orders.
        </p>
      </form>

      {result && <OrderView order={result.order} tracking={result.tracking} />}
    </div>
  )
}

export default TrackOrder
