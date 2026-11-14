import React, { useMemo } from 'react'
import { PayPalButtons, PayPalScriptProvider } from '@paypal/react-paypal-js'
import { api } from '../api'

// PayPal's own button only (no Pay Later, no card button: cards are paid with Stripe's field); OFS never sees the PayPal login.
const PayPalPayment = ({ clientId, currency, walletProblem, onToken, onProblem }) => {

  // Refuses to start a payment until the customer's details are complete.
  const handleClick = (data, actions) => {
    const problem = walletProblem()
    if (problem) {
      onProblem(problem)
      return actions.reject()
    }
    onProblem('')
    return actions.resolve()
  }

  // Asks our server to create the PayPal order; the server works out the amount from the cart.
  const createOrder = async () => {
    const data = await api('/api/payments/paypal/order', { method: 'POST' })
    return data.id
  }

  // Places the order once the customer has approved the payment at PayPal.
  const handleApprove = async (data) => {
    await onToken(`paypal:${data.orderID}`)
  }

  // Kept the same object between renders, or PayPal's script is reloaded and its button frame is torn down mid-load.
  const scriptOptions = useMemo(
    () => ({ clientId, currency, intent: 'capture', components: 'buttons', 'disable-funding': 'card,credit,paylater,venmo' }),
    [clientId, currency],
  )

  return (
    <div className="flex flex-col gap-3">
      <PayPalScriptProvider options={scriptOptions}>
        <PayPalButtons
          fundingSource="paypal"
          style={{ layout: 'vertical', shape: 'rect', label: 'pay' }}
          onClick={handleClick}
          createOrder={createOrder}
          onApprove={handleApprove}
          onCancel={() => onProblem('PayPal checkout was cancelled. Your cart has not changed.')}
          onError={(error) => onProblem(error?.message && !/Detected popup close/i.test(error.message) ? error.message : 'PayPal could not complete the payment. Please try again.')}
        />
      </PayPalScriptProvider>
    </div>
  )
}

export default PayPalPayment
