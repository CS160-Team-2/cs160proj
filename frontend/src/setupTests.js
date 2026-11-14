import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { vi } from 'vitest'

// Tests must not depend on a developer's own frontend/.env, so Stripe starts switched off in every test file.
vi.stubEnv('VITE_STRIPE_PUBLISHABLE_KEY', '')

afterEach(() => { cleanup()})