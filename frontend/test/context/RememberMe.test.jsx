// C9: the store sends the "Remember me" choice to the backend.
import React, { useContext } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import StoreContextProvider, { StoreContext } from '../../src/context/StoreContext'
import { api } from '../../src/api'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

// Buttons that call signIn and register through the store.
const Buttons = () => {
  const { signIn, register } = useContext(StoreContext)
  return (
    <>
      <button onClick={() => signIn('a@example.com', 'pw-long-1')}>default</button>
      <button onClick={() => signIn('a@example.com', 'pw-long-1', false)}>forget</button>
      <button onClick={() => register('Ann', 'a@example.com', 'pw-long-1', false)}>register</button>
    </>
  )
}

describe('remember me in the store', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.mockImplementation(async (path) => {
      if (path === '/api/products') return { products: [] }
      if (path === '/api/cart') return { cart: { items: [], item_count: 0 } }
      if (path === '/api/auth/me') return { user: null }
      return { user: { user_id: 1, role: 'customer' }, cart: { items: [], item_count: 0 } }
    })
  })

  // Presses a button and waits for the request it makes.
  async function press(name) {
    render(<StoreContextProvider><Buttons /></StoreContextProvider>)
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/me'))
    await act(async () => { screen.getByRole('button', { name }).click() })
  }

  test('signing in remembers by default', async () => {
    await press('default')
    expect(api).toHaveBeenCalledWith('/api/auth/login', { method: 'POST', body: { email: 'a@example.com', password: 'pw-long-1', remember: true } })
  })

  test('signing in can say not to remember', async () => {
    await press('forget')
    expect(api).toHaveBeenCalledWith('/api/auth/login', { method: 'POST', body: { email: 'a@example.com', password: 'pw-long-1', remember: false } })
  })

  test('registering sends the choice too', async () => {
    await press('register')
    expect(api).toHaveBeenCalledWith('/api/auth/register', { method: 'POST', body: { full_name: 'Ann', email: 'a@example.com', password: 'pw-long-1', remember: false } })
  })
})
