import React, { useContext, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { StoreContext } from '../context/StoreContext'
import TextContent from '../components/TextContent'

// Sign in or create an account on one page. After signing in, customers
// go back where they came from (?next=/checkout), or to the shop.
const Login = () => {

  const { signIn, register } = useContext(StoreContext)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const next = searchParams.get('next') || '/'

  const [mode, setMode] = useState('signin')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const creating = mode === 'register'

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const user = creating
        ? await register(fullName, email, password)
        : await signIn(email, password)
      // Staff have no shop pages yet; the dashboard is still to be built.
      navigate(user.role === 'customer' ? next : '/')
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const switchMode = () => {
    setMode(creating ? 'signin' : 'register')
    setError('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col items-center w-full sm:max-w-96 m-auto mt-14 gap-4 text-gray-800">
      <div className="text-3xl">
        <TextContent text1={creating ? 'CREATE' : 'SIGN'} text2={creating ? 'ACCOUNT' : 'IN'} />
      </div>

      {creating && (
        <input
          className="w-full px-3 py-2 border border-gray-800"
          type="text"
          placeholder="Full name"
          autoComplete="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
      )}
      <input
        className="w-full px-3 py-2 border border-gray-800"
        type="email"
        placeholder="Email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      <input
        className="w-full px-3 py-2 border border-gray-800"
        type="password"
        placeholder={creating ? 'Password (at least 8 characters)' : 'Password'}
        autoComplete={creating ? 'new-password' : 'current-password'}
        minLength={creating ? 8 : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />

      {error && <p className="w-full text-sm text-red-600" role="alert">{error}</p>}

      <div className="w-full flex justify-end text-sm -mt-2">
        <button type="button" onClick={switchMode} className="text-green-600 underline cursor-pointer">
          {creating ? 'Already have an account? Sign in' : 'New here? Create an account'}
        </button>
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="bg-green-600 text-white font-light px-8 py-2 mt-2 active:bg-green-400 disabled:opacity-60"
      >
        {submitting ? 'Please wait...' : creating ? 'Create account' : 'Sign in'}
      </button>
    </form>
  )
}

export default Login
