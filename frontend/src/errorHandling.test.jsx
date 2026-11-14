// C6: unknown pages, ended sessions, crashes and friendly errors on the customer pages.
import React, { useContext } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import App from './App'
import Login from './pages/Login'
import { OrderDetail, OrderHistory } from './pages/Orders'
import Item from './pages/Item'
import ErrorBoundary from './components/ErrorBoundary'
import StoreContextProvider, { StoreContext } from './context/StoreContext'
import { api, ApiError } from './api'
import { SESSION_EXPIRED } from './sessionEvents'

window.scrollTo = vi.fn()

vi.mock('./api', async () => {
  const actual = await vi.importActual('./api')
  return { ...actual, api: vi.fn() }
})
vi.mock('./components/RelatedItems', () => ({ default: () => <div /> }))
vi.mock('./components/NavigationBar', () => ({ default: () => <nav /> }))
vi.mock('./components/Footer', () => ({ default: () => <footer /> }))

const customer = { user_id: 1, role: 'customer', full_name: 'Anna Rivera', email: 'anna@example.com', is_guest: false }

// Shows where the router is, so tests can check a redirect.
const Where = () => {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}

// Answers the store's startup requests; the signed-in user is a customer unless told otherwise.
function backend({ me = customer, extra = {} } = {}) {
  api.mockImplementation(async (path, options) => {
    if (extra[path]) return extra[path](options)
    if (path === '/api/products') return { products: [] }
    if (path === '/api/cart') return { cart: { items: [], item_count: 0, subtotal: '0.00', total_weight_lb: '0.00', delivery_fee: '0.00', estimated_total: '0.00' } }
    if (path === '/api/auth/me') {
      if (!me) throw new ApiError('Please sign in first', 'UNAUTHENTICATED', 401)
      return { user: me }
    }
    throw new Error(`Unexpected request ${path}`)
  })
}

// Draws the whole app at an address, with the real store.
function openApp(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <StoreContextProvider>
        <App />
        <Where />
      </StoreContextProvider>
    </MemoryRouter>,
  )
}

describe('unknown pages', () => {
  beforeEach(() => { vi.resetAllMocks(); backend() })

  test('an address the site does not have shows a 404 page with ways back', async () => {
    openApp('/no/such/page')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'GO TO HOME' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'BROWSE PRODUCTS' })).toHaveAttribute('href', '/products')
  })

  test('a product that does not exist says so once the products have loaded', async () => {
    openApp('/item/999')
    expect(await screen.findByRole('heading', { name: 'We could not find that product' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'BROWSE PRODUCTS' })).toBeInTheDocument()
  })
})

describe('an ended session', () => {
  beforeEach(() => { vi.resetAllMocks(); backend() })

  test('on a page that needs sign-in the customer is sent to sign in, with a notice and a way back', async () => {
    openApp('/account')
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/me'))
    await act(async () => { window.dispatchEvent(new Event(SESSION_EXPIRED)) })

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/login?next=%2Faccount&expired=1'))
    expect(await screen.findByRole('status')).toHaveTextContent('Your session ended')
  })

  test('on a public page a banner offers to sign in again and can be dismissed', async () => {
    const user = userEvent.setup()
    openApp('/products')
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/me'))
    await act(async () => { window.dispatchEvent(new Event(SESSION_EXPIRED)) })

    expect(await screen.findByText(/Your session ended, so you have been signed out/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in again' })).toHaveAttribute('href', '/login?next=%2Fproducts&expired=1')
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument()
  })

  test('nothing happens for someone who was not signed in', async () => {
    backend({ me: null })
    openApp('/orders/OFS-1')
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/me'))
    await act(async () => { window.dispatchEvent(new Event(SESSION_EXPIRED)) })
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument()
  })

  test('a guest whose session ended just starts over without a notice', async () => {
    backend({ me: { ...customer, is_guest: true } })
    openApp('/products')
    await waitFor(() => expect(api).toHaveBeenCalledWith('/api/auth/me'))
    await act(async () => { window.dispatchEvent(new Event(SESSION_EXPIRED)) })
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument()
  })

  test('signing out on purpose shows no notice', async () => {
    const user = userEvent.setup()
    backend({ extra: { '/api/auth/logout': async () => ({ ok: true }) } })
    // A button that signs out through the store.
    const SignOutButton = () => <button onClick={useContext(StoreContext).signOut}>Sign out</button>
    render(
      <MemoryRouter initialEntries={['/orders']}>
        <StoreContextProvider><SignOutButton /><App /></StoreContextProvider>
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument()
  })
})

describe('the sign-in page', () => {
  // Draws the sign-in page at an address and shows where a successful sign-in goes.
  function openLogin(url) {
    const signIn = vi.fn().mockResolvedValue(customer)
    render(
      <StoreContext.Provider value={{ signIn, register: vi.fn(), dismissSessionExpired: vi.fn() }}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </StoreContext.Provider>,
    )
    return signIn
  }

  // Types credentials and presses Sign in.
  async function signInNow() {
    const user = userEvent.setup()
    await user.type(screen.getByPlaceholderText('Email'), 'anna@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
  }

  test('explains an ended session and returns the customer to where they were', async () => {
    openLogin('/login?next=%2Forders%2FOFS-1&expired=1')
    expect(screen.getByRole('status')).toHaveTextContent('Your session ended')
    await signInNow()
    expect(await screen.findByTestId('where')).toHaveTextContent('/orders/OFS-1')
  })

  test('shows no notice on a normal visit', () => {
    openLogin('/login')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  test.each(['//evil.example', 'https://evil.example'])('ignores an unsafe next value %s', async (next) => {
    openLogin(`/login?next=${encodeURIComponent(next)}`)
    await signInNow()
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/$/)
  })
})

describe('order pages show friendly errors', () => {
  beforeEach(() => vi.resetAllMocks())

  // Draws the order pages for a signed-in customer.
  function openOrders(url) {
    render(
      <StoreContext.Provider value={{ user: customer, currency: '$' }}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/orders" element={<OrderHistory />} />
            <Route path="/orders/:orderNumber" element={<OrderDetail />} />
          </Routes>
        </MemoryRouter>
      </StoreContext.Provider>,
    )
  }

  test('an order that is not on the account says so and links to the order list', async () => {
    api.mockRejectedValue(new ApiError('Order not found', 'NOT_FOUND', 404))
    openOrders('/orders/OFS-NOPE')
    expect(await screen.findByRole('heading', { name: 'We could not find that order' })).toBeInTheDocument()
    expect(screen.getByText(/There is no order OFS-NOPE on your account/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SEE ALL MY ORDERS' })).toHaveAttribute('href', '/orders')
    expect(screen.queryByRole('button', { name: 'TRY AGAIN' })).not.toBeInTheDocument()
  })

  test('an order that fails to load offers Try again, which loads it', async () => {
    const user = userEvent.setup()
    api.mockRejectedValue(new ApiError('We cannot reach the store right now.', 'NETWORK', 0))
    openOrders('/orders/OFS-TEST001')
    expect(await screen.findByRole('heading', { name: 'We could not load your order' })).toBeInTheDocument()

    api.mockImplementation(async (path) => {
      if (path.endsWith('/tracking')) return { status: 'placed', steps: [], estimated_arrival: null, map: null }
      return { order: { order_number: 'OFS-TEST001', placed_at: '2026-10-20T18:00:00Z', items: [], address: {}, payment: {}, subtotal: '0', total_weight_lb: '0', delivery_fee: '0', tax: '0', grand_total: '0' } }
    })
    await user.click(screen.getByRole('button', { name: 'TRY AGAIN' }))
    expect(await screen.findByText('OFS-TEST001')).toBeInTheDocument()
  })

  test('the order list that fails to load offers Try again and a link into the shop', async () => {
    api.mockRejectedValue(new ApiError('We cannot reach the store right now.', 'NETWORK', 0))
    openOrders('/orders')
    expect(await screen.findByRole('heading', { name: 'We could not load your orders' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'TRY AGAIN' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'BROWSE PRODUCTS' })).toHaveAttribute('href', '/products')
  })
})

describe('a page that crashes', () => {
  // A component that always throws while drawing.
  const Broken = () => { throw new Error('boom') }

  test('shows a way out instead of a blank screen', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <MemoryRouter>
        <ErrorBoundary><Broken /></ErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'RELOAD PAGE' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'GO TO HOME' })).toHaveAttribute('href', '/')
    vi.restoreAllMocks()
  })

  test('draws its children normally when nothing is wrong', () => {
    render(<MemoryRouter><ErrorBoundary><p>All fine</p></ErrorBoundary></MemoryRouter>)
    expect(screen.getByText('All fine')).toBeInTheDocument()
  })
})
