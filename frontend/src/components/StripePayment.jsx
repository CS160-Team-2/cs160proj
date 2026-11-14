import React, { useEffect, useState } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, ExpressCheckoutElement, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { CardIcon, LockIcon } from './Icons'

// Reads the public Stripe key from frontend/.env; empty when Stripe is not set up.
export const stripePublishableKey = () => (import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '').trim()

let stripePromise = null

// Loads Stripe.js once and reuses it.
const getStripe = () => {
  if (!stripePromise) stripePromise = loadStripe(stripePublishableKey())
  return stripePromise
}

// Turns a money string such as "12.34" into whole cents without floating-point maths.
export const toCents = (amount) => {
  const [dollars, cents = ''] = String(amount).split('.')
  return Number(dollars) * 100 + Number((cents + '00').slice(0, 2))
}

// Stripe's card field and the Apple Pay / Google Pay buttons; the card number never reaches our page or server.
const StripeFields = ({ billing, tokenGetterRef, walletProblem, onWalletToken, onWalletError }) => {

  const stripe = useStripe()
  const elements = useElements()
  const [walletsShown, setWalletsShown] = useState(false)

  // Turns what the customer typed into a Stripe PaymentMethod id (pm_...), or throws Stripe's own message.
  const createPaymentMethodId = async (billingDetails) => {
    const { error: submitError } = await elements.submit()
    if (submitError) throw new Error(submitError.message)
    const { paymentMethod, error } = await stripe.createPaymentMethod({ elements, params: { billing_details: billingDetails } })
    if (error) throw new Error(error.message)
    return paymentMethod.id
  }

  useEffect(() => {
    tokenGetterRef.current = () => createPaymentMethodId(billing)
    return () => { tokenGetterRef.current = null }
  })

  // Opens the wallet sheet only when the customer's details are complete.
  const handleWalletClick = (event) => {
    const problem = walletProblem()
    if (problem) {
      onWalletError(problem)
      return
    }
    event.resolve()
  }

  // Creates the PaymentMethod from the wallet sheet and places the order with it.
  const handleWalletConfirm = async (event) => {
    try {
      const token = await createPaymentMethodId({ ...billing, ...(event.billingDetails || {}) })
      if (!(await onWalletToken(token))) event.paymentFailed({ reason: 'fail' })
    } catch (err) {
      event.paymentFailed({ reason: 'fail' })
      onWalletError(err.message)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className={walletsShown ? 'flex flex-col gap-3' : 'hidden'}>
        <ExpressCheckoutElement
          onClick={handleWalletClick}
          onConfirm={handleWalletConfirm}
          onReady={({ availablePaymentMethods }) => setWalletsShown(Boolean(availablePaymentMethods))}
          options={{
            buttonHeight: 44,
            paymentMethods: { applePay: 'auto', googlePay: 'auto', link: 'never', paypal: 'never', amazonPay: 'never' },
          }}
        />
        <p className="text-xs text-gray-500 text-center">or pay with a card</p>
      </div>
      <PaymentElement
        options={{
          layout: 'tabs',
          fields: { billingDetails: { name: 'never', email: 'never' } },
        }}
      />
    </div>
  )
}

// The card section of checkout when Stripe is on: Stripe's own fields inside a labelled box.
const StripePayment = ({ amountText, currency, billing, tokenGetterRef, walletProblem, onWalletToken, onWalletError }) => {

  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    getStripe().then((stripe) => { if (!stripe) setLoadFailed(true) }).catch(() => setLoadFailed(true))
  }, [])

  const cents = toCents(amountText)

  return (
    <div className="flex flex-col gap-3 border border-gray-300 rounded px-4 py-4">
      <div className="flex items-center justify-between text-sm text-gray-700">
        <p className="font-medium flex items-center gap-2"><CardIcon className="w-5" /> Pay with card or wallet</p>
        <p className="flex items-center gap-1 text-xs text-gray-500"><LockIcon className="w-3.5" /> Secure payment by Stripe</p>
      </div>
      {loadFailed && (
        <p className="text-sm text-red-600" role="alert">We could not load the payment form. Check your connection and any ad blocker, then reload the page.</p>
      )}
      {!loadFailed && cents > 0 && (
        <Elements
          stripe={getStripe()}
          options={{ mode: 'payment', amount: cents, currency, paymentMethodCreation: 'manual', paymentMethodTypes: ['card'] }}
        >
          <StripeFields
            billing={billing}
            tokenGetterRef={tokenGetterRef}
            walletProblem={walletProblem}
            onWalletToken={onWalletToken}
            onWalletError={onWalletError}
          />
        </Elements>
      )}
    </div>
  )
}

export default StripePayment
