import React, { useContext, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import { api } from '../api'
import TextContent from '../components/TextContent'

const emptyAddress = { street: '', city: '', state: 'CA', zip_code: '' }

// Shows a green or red feedback line under a form.
const Message = ({ message }) => (
  message.text ? <p className={`text-sm ${message.error ? 'text-red-600' : 'text-green-600'}`} role={message.error ? 'alert' : 'status'}>{message.text}</p> : null
)

// A titled box that groups one part of the account page.
const Section = ({ title, children }) => (
  <section className="flex flex-col gap-4 border border-gray-200 px-5 py-5">
    <h2 className="text-lg font-medium">{title}</h2>
    {children}
  </section>
)

const inputClass = 'border border-gray-300 px-3 py-2 w-full'

// Form to edit the customer's name, email and phone.
const Details = ({ user, updateUser }) => {

  const [form, setForm] = useState({ full_name: user.full_name, phone: user.phone || '', email: user.email })
  const [message, setMessage] = useState({ text: '', error: false })
  const [busy, setBusy] = useState(false)

  // Updates one field of the details form as the customer types.
  const change = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // Saves the details and refreshes the signed-in user.
  const save = async (event) => {
    event.preventDefault()
    if (!form.full_name.trim()) {
      setMessage({ text: 'Enter your name.', error: true })
      return
    }
    setBusy(true)
    try {
      const data = await api('/api/users/me', {
        method: 'PATCH',
        body: { full_name: form.full_name.trim(), phone: form.phone.trim() || null, email: form.email.trim() },
      })
      updateUser(data.user)
      setMessage({ text: 'Your details were saved.', error: false })
    } catch (err) {
      setMessage({ text: err.message, error: true })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Your details">
      <form onSubmit={save} className="flex flex-col gap-3 sm:max-w-md">
        <label className="text-sm text-gray-600">Full name
          <input className={`${inputClass} mt-1`} type="text" autoComplete="name" value={form.full_name} onChange={change('full_name')} />
        </label>
        <label className="text-sm text-gray-600">Email
          <input className={`${inputClass} mt-1`} type="email" autoComplete="email" value={form.email} onChange={change('email')} />
        </label>
        <label className="text-sm text-gray-600">Phone (optional)
          <input className={`${inputClass} mt-1`} type="tel" autoComplete="tel" value={form.phone} onChange={change('phone')} />
        </label>
        <Message message={message} />
        <button type="submit" disabled={busy} className="self-start bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400 disabled:opacity-60">
          {busy ? 'Saving...' : 'SAVE DETAILS'}
        </button>
      </form>
    </Section>
  )
}

// Form to change the password; asks for the current one first.
const Password = () => {

  const [form, setForm] = useState({ current: '', next: '', again: '' })
  const [message, setMessage] = useState({ text: '', error: false })
  const [busy, setBusy] = useState(false)

  // Updates one password field as the customer types.
  const change = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // Checks the new password, then sends the change to the backend.
  const save = async (event) => {
    event.preventDefault()
    if (form.next.length < 8) {
      setMessage({ text: 'The new password must be at least 8 characters.', error: true })
      return
    }
    if (form.next !== form.again) {
      setMessage({ text: 'The new passwords do not match.', error: true })
      return
    }
    setBusy(true)
    try {
      await api('/api/users/me', { method: 'PATCH', body: { current_password: form.current, new_password: form.next } })
      setForm({ current: '', next: '', again: '' })
      setMessage({ text: 'Your password was changed.', error: false })
    } catch (err) {
      setMessage({ text: err.message, error: true })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Change password">
      <form onSubmit={save} className="flex flex-col gap-3 sm:max-w-md">
        <input className={inputClass} type="password" placeholder="Current password" aria-label="Current password" autoComplete="current-password" value={form.current} onChange={change('current')} />
        <input className={inputClass} type="password" placeholder="New password (at least 8 characters)" aria-label="New password" autoComplete="new-password" value={form.next} onChange={change('next')} />
        <input className={inputClass} type="password" placeholder="Repeat the new password" aria-label="Repeat the new password" autoComplete="new-password" value={form.again} onChange={change('again')} />
        <Message message={message} />
        <button type="submit" disabled={busy} className="self-start bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400 disabled:opacity-60">
          {busy ? 'Saving...' : 'CHANGE PASSWORD'}
        </button>
      </form>
    </Section>
  )
}

// Street, city, state and ZIP fields shared by add and edit.
const AddressForm = ({ initial, submitLabel, onSubmit, onCancel }) => {

  const [form, setForm] = useState(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Updates one address field as the customer types.
  const change = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // Validates the address and passes it to the save callback.
  const submit = async (event) => {
    event.preventDefault()
    const values = Object.fromEntries(Object.entries(form).map(([name, value]) => [name, value.trim()]))
    if (!values.street || !values.city || !values.state) {
      setError('Enter the full address.')
      return
    }
    if (!/^\d{5}(-\d{4})?$/.test(values.zip_code)) {
      setError('Enter a 5 digit ZIP code.')
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
    <form onSubmit={submit} className="flex flex-col gap-3 sm:max-w-md">
      <input className={inputClass} placeholder="Street address" aria-label="Street address" autoComplete="street-address" value={form.street} onChange={change('street')} />
      <div className="flex gap-3">
        <input className={inputClass} placeholder="City" aria-label="City" autoComplete="address-level2" value={form.city} onChange={change('city')} />
        <input className={inputClass} placeholder="State" aria-label="State" autoComplete="address-level1" maxLength={50} value={form.state} onChange={change('state')} />
        <input className={inputClass} placeholder="ZIP" aria-label="ZIP" autoComplete="postal-code" inputMode="numeric" value={form.zip_code} onChange={change('zip_code')} />
      </div>
      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      <div className="flex gap-3">
        <button type="submit" disabled={busy} className="bg-green-600 text-white text-sm px-6 py-2 active:bg-green-400 disabled:opacity-60">{busy ? 'Saving...' : submitLabel}</button>
        <button type="button" onClick={onCancel} className="border text-sm px-6 py-2">CANCEL</button>
      </div>
    </form>
  )
}

// One saved address with edit and delete (with confirmation).
const AddressRow = ({ address, onChanged }) => {

  const [mode, setMode] = useState('view')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Sends the edited address; the backend keeps past orders' address unchanged.
  const save = async (values) => {
    await api(`/api/users/me/addresses/${address.address_id}`, { method: 'PATCH', body: values })
    setMode('view')
    onChanged()
  }

  // Deletes the address after the customer confirms.
  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/users/me/addresses/${address.address_id}`, { method: 'DELETE' })
      onChanged()
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  if (mode === 'edit') {
    return (
      <div className="border border-gray-200 px-4 py-4">
        <p className="text-sm font-medium mb-3">Edit address</p>
        <AddressForm
          initial={{ street: address.street, city: address.city, state: address.state, zip_code: address.zip_code }}
          submitLabel="SAVE ADDRESS"
          onSubmit={save}
          onCancel={() => setMode('view')}
        />
      </div>
    )
  }

  return (
    <div className="border border-gray-200 px-4 py-3 flex flex-col gap-2">
      <p className="text-sm text-gray-700">{address.street}, {address.city}, {address.state} {address.zip_code}</p>
      {mode === 'delete' ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <p className="text-gray-700">Delete this address?</p>
          <button onClick={remove} disabled={busy} className="bg-red-600 text-white px-4 py-1 disabled:opacity-60">YES, DELETE</button>
          <button onClick={() => { setMode('view'); setError('') }} className="border px-4 py-1">KEEP IT</button>
        </div>
      ) : (
        <div className="flex gap-2">
          <button onClick={() => setMode('edit')} className="border text-sm px-4 py-1">EDIT</button>
          <button onClick={() => setMode('delete')} className="border text-sm px-4 py-1">DELETE</button>
        </div>
      )}
      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
    </div>
  )
}

// Lists saved addresses and lets the customer add one.
const Addresses = () => {

  const [addresses, setAddresses] = useState(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  // Fetches the customer's saved addresses.
  const load = () => {
    api('/api/users/me/addresses')
      .then((data) => {
        setAddresses(data.addresses)
        setError('')
      })
      .catch((err) => setError(err.message))
  }

  useEffect(load, [])

  // Saves a new address and reloads the list.
  const add = async (values) => {
    await api('/api/users/me/addresses', { method: 'POST', body: values })
    setAdding(false)
    load()
  }

  return (
    <Section title="Saved addresses">
      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      {addresses && addresses.length === 0 && !adding && <p className="text-sm text-gray-600">You have no saved addresses.</p>}
      {addresses && addresses.map((address) => (
        <AddressRow key={address.address_id} address={address} onChanged={load} />
      ))}
      {adding ? (
        <div className="border border-gray-200 px-4 py-4">
          <p className="text-sm font-medium mb-3">New address</p>
          <AddressForm initial={emptyAddress} submitLabel="SAVE ADDRESS" onSubmit={add} onCancel={() => setAdding(false)} />
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="self-start text-sm text-green-600 underline">+ Add a new address</button>
      )}
    </Section>
  )
}

// Asks for a password before closing the account.
const DeleteAccount = ({ onDeleted }) => {

  const [confirming, setConfirming] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Closes the confirmation box and clears the password.
  const cancel = () => {
    setConfirming(false)
    setPassword('')
    setError('')
  }

  // Deletes the account, then tells the page it is done.
  const remove = async (event) => {
    event.preventDefault()
    if (!password) {
      setError('Enter your password to confirm.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api('/api/users/me', { method: 'DELETE', body: { password } })
      await onDeleted()
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Section title="Delete account">
      {confirming ? (
        <form onSubmit={remove} className="flex flex-col gap-3 sm:max-w-md border border-red-300 bg-red-50 px-4 py-4" role="alertdialog" aria-label="Confirm account deletion">
          <p className="text-sm font-medium text-red-700">Delete your account?</p>
          <p className="text-sm text-gray-700">
            This closes your account and removes your saved addresses and cart. Your past orders are kept for our records. You cannot undo this.
          </p>
          <input className={inputClass} type="password" placeholder="Enter your password to confirm" aria-label="Password to confirm" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          <div className="flex gap-3">
            <button type="submit" disabled={busy} className="bg-red-600 text-white text-sm px-6 py-2 disabled:opacity-60">{busy ? 'Deleting...' : 'YES, DELETE MY ACCOUNT'}</button>
            <button type="button" onClick={cancel} className="border text-sm px-6 py-2 bg-white">CANCEL</button>
          </div>
        </form>
      ) : (
        <>
          <p className="text-sm text-gray-600">Close your account and remove your saved information.</p>
          <button onClick={() => setConfirming(true)} className="self-start border border-red-600 text-red-600 text-sm px-6 py-2 hover:bg-red-50">DELETE MY ACCOUNT</button>
        </>
      )}
    </Section>
  )
}

// The /account page: details, password, addresses and delete account.
const Account = () => {

  const { user, updateUser, signOut } = useContext(StoreContext)
  const navigate = useNavigate()

  if (user === undefined) return null
  if (!user) return <Navigate to="/login?next=/account" replace />
  if (user.role !== 'customer' || user.is_guest) return <Navigate to={user.role === 'customer' ? '/orders' : '/'} replace />

  // Signs out and returns Home with the 'account deleted' message.
  const deleted = async () => {
    await signOut()
    navigate('/', { state: { accountDeleted: true } })
  }

  return (
    <div className="border-t-2 pt-14 flex flex-col gap-8 pb-10">
      <div className="text-2xl">
        <TextContent text1={'MY'} text2={'ACCOUNT'} />
      </div>
      <Details user={user} updateUser={updateUser} />
      <Password />
      <Addresses />
      <DeleteAccount onDeleted={deleted} />
    </div>
  )
}

export default Account
