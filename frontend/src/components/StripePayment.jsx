import React, { useEffect, useState } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { CardElement, Elements, ExpressCheckoutElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { CardIcon, LockIcon } from './Icons'

// Reads the public Stripe key from frontend/.env; empty when Stripe is not set up.
export const stripePublishableKey = () => (import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '').trim()

let stripePromise = null

// Loads Stripe.js once and reuses it, with Stripe's test-mode debugging badge turned off.
const getStripe = () => {
  if (!stripePromise) stripePromise = loadStripe(stripePublishableKey(), { developerTools: { assistant: { enabled: false } } })
  return stripePromise
}

// Turns a money string such as "12.34" into whole cents without floating-point maths.
export const toCents = (amount) => {
  const [dollars, cents = ''] = String(amount).split('.')
  return Number(dollars) * 100 + Number((cents + '00').slice(0, 2))
}

const cardStyle = {
  base: { fontSize: '16px', color: '#374151', '::placeholder': { color: '#9ca3af' } },
  invalid: { color: '#dc2626' },
}

// Stripe's card-only field (number, expiry, CVC, ZIP); the card number never reaches our page or server.
const CardField = ({ billing, tokenGetterRef, onLoadError }) => {

  const stripe = useStripe()
  const elements = useElements()
  const [cardMessage, setCardMessage] = useState('')

  // Turns what the customer typed into a Stripe PaymentMethod id (pm_...), or throws Stripe's own message.
  const createPaymentMethodId = async () => {
    const { paymentMethod, error } = await stripe.createPaymentMethod({
      type: 'card',
      card: elements.getElement(CardElement),
      billing_details: billing,
    })
    if (error) throw new Error(error.message)
    return paymentMethod.id
  }

  useEffect(() => {
    tokenGetterRef.current = createPaymentMethodId
    return () => { tokenGetterRef.current = null }
  })

  return (
    <div className="flex flex-col gap-2">
      <div className="border border-gray-300 rounded px-3.5 py-3">
        <CardElement
          options={{ style: cardStyle, disableLink: true }}
          onChange={(event) => setCardMessage(event.error ? event.error.message : '')}
          onLoadError={(event) => onLoadError(event.error?.message || 'The card form could not be loaded.')}
        />
      </div>
      {cardMessage && <p className="text-sm text-red-600" role="alert">{cardMessage}</p>}
    </div>
  )
}

// The Apple Pay / Google Pay buttons; they appear only where the browser and device support them.
const WalletButtons = ({ billing, walletProblem, onWalletToken, onWalletError }) => {

  const stripe = useStripe()
  const elements = useElements()
  const [walletsShown, setWalletsShown] = useState(false)

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
      const { error: submitError } = await elements.submit()
      if (submitError) throw new Error(submitError.message)
      const { paymentMethod, error } = await stripe.createPaymentMethod({
        elements,
        params: { billing_details: { ...billing, ...(event.billingDetails || {}) } },
      })
      if (error) throw new Error(error.message)
      if (!(await onWalletToken(paymentMethod.id))) event.paymentFailed({ reason: 'fail' })
    } catch (err) {
      event.paymentFailed({ reason: 'fail' })
      onWalletError(err.message)
    }
  }

  return (
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
  )
}

// The card section of checkout when Stripe is on: wallet buttons, then Stripe's card field, in a labelled box.
const StripePayment = ({ amountText, currency, billing, tokenGetterRef, walletProblem, onWalletToken, onWalletError }) => {

  const [loadFailed, setLoadFailed] = useState(false)
  const [cardLoadError, setCardLoadError] = useState('')

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
      {cardLoadError && (
        <p className="text-sm text-red-600" role="alert">The card form could not be loaded: {cardLoadError}</p>
      )}
      {!loadFailed && cents > 0 && (
        <>
          <Elements stripe={getStripe()} options={{ mode: 'payment', amount: cents, currency, paymentMethodCreation: 'manual' }}>
            <WalletButtons
              billing={billing}
              walletProblem={walletProblem}
              onWalletToken={onWalletToken}
              onWalletError={onWalletError}
            />
          </Elements>
          <Elements stripe={getStripe()}>
            <CardField billing={billing} tokenGetterRef={tokenGetterRef} onLoadError={setCardLoadError} />
          </Elements>
        </>
      )}
    </div>
  )
}

export default StripePayment
