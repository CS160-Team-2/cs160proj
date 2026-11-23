import React from 'react'
import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import NavigationBar from '../../src/components/NavigationBar'
import Footer from '../../src/components/Footer'
import StoreHero from '../../src/components/StoreHero'
import { StoreContext } from '../../src/context/StoreContext'

// Draws the top bar for the given user (null means signed out).
function renderBar(user, signOut = vi.fn().mockResolvedValue(undefined)) {
  render(
    <StoreContext.Provider value={{ user, signOut, getShoppingCartCount: () => 0 }}>
      <MemoryRouter><NavigationBar /></MemoryRouter>
    </StoreContext.Provider>,
  )
  return signOut
}

const customer = { role: 'customer', full_name: 'Anna Rivera', is_guest: false }

describe('top bar links', () => {
  test('shows Track and Orders and no About or Contact', () => {
    renderBar(null)

    expect(screen.getByRole('link', { name: 'TRACK' })).toHaveAttribute('href', '/track-order')
    expect(screen.getByRole('link', { name: 'ORDERS' })).toHaveAttribute('href', '/orders')
    expect(screen.queryByText('ABOUT')).not.toBeInTheDocument()
    expect(screen.queryByText('CONTACT')).not.toBeInTheDocument()
  })

  test('staff do not see the customer Track and Orders links', () => {
    renderBar({ role: 'employee', full_name: 'Bob' })

    expect(screen.queryByRole('link', { name: 'TRACK' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'ORDERS' })).not.toBeInTheDocument()
  })
})

describe('account menu', () => {
  test('signed out: only Sign in', async () => {
    renderBar(null)
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))

    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
  })

  test('a guest session is treated as signed out', async () => {
    renderBar({ ...customer, is_guest: true })
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))

    expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Profile' })).not.toBeInTheDocument()
  })

  test('customer: Profile (not the name) and Sign out', async () => {
    const signOut = renderBar(customer)
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))

    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute('href', '/account')
    expect(screen.queryByText('Anna Rivera')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Sign in' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(signOut).toHaveBeenCalled()
  })

  test('employee sees only staff pages and Sign out', async () => {
    renderBar({ role: 'employee', full_name: 'Bob' })
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))

    expect(screen.getByRole('link', { name: 'Inventory' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Customer orders' })).toHaveAttribute('href', '/staff/orders')
    expect(screen.getByRole('link', { name: 'Delivery tracking' })).toHaveAttribute('href', '/delivery')
    expect(screen.queryByRole('link', { name: 'Manager dashboard' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Profile' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  test('manager also sees the dashboard and staff accounts', async () => {
    renderBar({ role: 'manager', full_name: 'Emily' })
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))

    expect(screen.getByRole('link', { name: 'Manager dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Staff accounts' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Delivery tracking' })).toHaveAttribute('href', '/manager/delivery')
  })
})

describe('footer and hero', () => {
  test('footer carries About OFS, Contact details and the copyright line', () => {
    render(<MemoryRouter><Footer /></MemoryRouter>)
    expect(screen.getByAltText('OFS')).toBeInTheDocument()

    expect(screen.getByRole('heading', { name: 'ABOUT' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'CONTACT' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /@ofs-organic\.example/ })).toHaveAttribute('href', expect.stringMatching(/^mailto:/))
    expect(screen.getByRole('link', { name: /555-0142/ })).toHaveAttribute('href', expect.stringMatching(/^tel:/))
    expect(screen.getByText('Copyright 2026 OFS - All Rights Reserved.')).toBeInTheDocument()
  })

  test('hero shows the mission in a black-to-green gradient, in a 70% white box with a green border, and no logo', () => {
    render(<StoreHero />)

    const mission = screen.getByRole('heading', { name: /Fresh organic groceries, delivered to your door/ })
    expect(mission).toHaveClass('from-black', 'to-green-600', 'text-transparent')
    expect(screen.queryByAltText('OFS')).not.toBeInTheDocument()
    expect(mission.parentElement).toHaveClass('bg-white/70')
    expect(screen.queryByText('OUR MISSION')).not.toBeInTheDocument()
    expect(mission.parentElement).toHaveClass('border-green-600')
  })
})
