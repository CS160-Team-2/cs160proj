// C9: the "Remember me" box on the sign-in and register form.
import React from 'react'
import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Login from '../../src/pages/Login'
import { StoreContext } from '../../src/context/StoreContext'

// Draws the sign-in page with stand-in sign-in functions.
function renderLogin() {
  const context = {
    signIn: vi.fn().mockResolvedValue({ role: 'customer' }),
    register: vi.fn().mockResolvedValue({ role: 'customer' }),
    dismissSessionExpired: vi.fn(),
  }
  render(<StoreContext.Provider value={context}><MemoryRouter><Login /></MemoryRouter></StoreContext.Provider>)
  return context
}

describe('Remember me', () => {
  test('is ticked to start with and is sent as true when signing in', async () => {
    const user = userEvent.setup()
    const { signIn } = renderLogin()
    expect(screen.getByRole('checkbox', { name: /Remember me/ })).toBeChecked()

    await user.type(screen.getByPlaceholderText('Email'), 'a@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(signIn).toHaveBeenCalledWith('a@example.com', 'long-enough-1', true)
  })

  test('unticking it sends false when signing in', async () => {
    const user = userEvent.setup()
    const { signIn } = renderLogin()
    await user.click(screen.getByRole('checkbox', { name: /Remember me/ }))

    await user.type(screen.getByPlaceholderText('Email'), 'a@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(signIn).toHaveBeenCalledWith('a@example.com', 'long-enough-1', false)
  })

  test('the same choice is sent when creating an account', async () => {
    const user = userEvent.setup()
    const { register } = renderLogin()
    await user.click(screen.getByRole('button', { name: 'New here? Create an account' }))
    await user.click(screen.getByRole('checkbox', { name: /Remember me/ }))

    await user.type(screen.getByPlaceholderText('Full name'), 'Ann Lee')
    await user.type(screen.getByPlaceholderText('Email'), 'a@example.com')
    await user.type(screen.getByPlaceholderText(/^Password/), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(register).toHaveBeenCalledWith('Ann Lee', 'a@example.com', 'long-enough-1', false)
  })
})

// C10: after too many wrong passwords the customer is told to wait, in the server's own words.
describe('Too many wrong passwords', () => {
  test('shows the wait message and keeps the form', async () => {
    const user = userEvent.setup()
    const { signIn } = renderLogin()
    signIn.mockRejectedValue(Object.assign(new Error('Too many failed sign-in attempts for this account. Please wait 10 minutes and try again.'), { status: 429, code: 'RATE_LIMITED' }))

    await user.type(screen.getByPlaceholderText('Email'), 'a@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'wrong-wrong-1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/Please wait 10 minutes and try again/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Email')).toHaveValue('a@example.com')
  })
})

