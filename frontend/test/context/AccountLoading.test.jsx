import React, { useContext } from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import StoreContextProvider, { StoreContext } from '../../src/context/StoreContext'
import { api } from '../../src/api'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

// Shows what the store currently knows about who is signed in.
const Who = () => {
  const { user } = useContext(StoreContext)
  return <p>{user === undefined ? 'not known yet' : user === null ? 'signed out' : `signed in as ${user.full_name}`}</p>
}

const unreachable = () => Object.assign(new Error('We cannot reach the store right now.'), { status: 0, code: 'NETWORK' })

// Answers every request except /api/auth/me normally; me is answered by the given function.
function backend(me) {
  api.mockImplementation(async (path) => {
    if (path === '/api/auth/me') return me()
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00', can_check_out: false } }
    throw new Error(`Unexpected ${path}`)
  })
}

describe('who is signed in', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers({ shouldAdvanceTime: true }) })
  afterEach(() => vi.useRealTimers())

  test('stays unknown while the store cannot be reached, then is found out when it comes back', async () => {
    let down = true
    backend(async () => {
      if (down) throw unreachable()
      return { user: { user_id: 1, full_name: 'Anna Rivera', role: 'customer' } }
    })
    render(<StoreContextProvider><Who /></StoreContextProvider>)

    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(screen.getByText('not known yet')).toBeInTheDocument()

    down = false
    await act(async () => { await vi.advanceTimersByTimeAsync(5200) })
    expect(await screen.findByText('signed in as Anna Rivera')).toBeInTheDocument()
  })

  test('a plain "not signed in" answer is signed out, not a reason to keep asking', async () => {
    backend(async () => { throw Object.assign(new Error('Please sign in'), { status: 401, code: 'UNAUTHENTICATED' }) })
    render(<StoreContextProvider><Who /></StoreContextProvider>)

    expect(await screen.findByText('signed out')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
    expect(api.mock.calls.filter(([path]) => path === '/api/auth/me')).toHaveLength(1)
  })

  test('a server error is treated like the store being out of reach', async () => {
    backend(async () => { throw Object.assign(new Error('Something went wrong'), { status: 503, code: 'ERROR' }) })
    render(<StoreContextProvider><Who /></StoreContextProvider>)

    await act(async () => { await vi.advanceTimersByTimeAsync(5200) })

    expect(screen.getByText('not known yet')).toBeInTheDocument()
    expect(api.mock.calls.filter(([path]) => path === '/api/auth/me').length).toBeGreaterThan(1)
  })
})
