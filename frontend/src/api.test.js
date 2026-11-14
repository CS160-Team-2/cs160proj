import { afterEach, describe, expect, test, vi } from 'vitest'
import { api, ApiError } from './api'
import { SESSION_EXPIRED } from './sessionEvents'

// Makes fetch answer with a status and JSON body.
const reply = (status, body) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body }))

describe('api client errors', () => {
  afterEach(() => vi.unstubAllGlobals())

  test('returns the data on success', async () => {
    reply(200, { ok: true, value: 7 })
    expect((await api('/api/x')).value).toBe(7)
  })

  test('throws the backend message, code and status', async () => {
    reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'Order not found' } })
    await expect(api('/api/x')).rejects.toMatchObject({ message: 'Order not found', code: 'NOT_FOUND', status: 404 })
  })

  test('falls back to a plain message when the reply is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error('bad') } }))
    await expect(api('/api/x')).rejects.toMatchObject({ message: 'Something went wrong', status: 502 })
  })

  test('says the store cannot be reached when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await api('/api/x').catch((err) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('NETWORK')
    expect(error.message).toMatch(/internet connection/)
  })

  test('sends a JSON body, and leaves FormData alone', async () => {
    reply(200, { ok: true })
    await api('/api/x', { method: 'POST', body: { a: 1 } })
    expect(fetch.mock.calls[0][1]).toMatchObject({ body: '{"a":1}', headers: { 'Content-Type': 'application/json' } })
    const form = new FormData()
    await api('/api/y', { method: 'POST', body: form })
    expect(fetch.mock.calls[1][1].body).toBe(form)
    expect(fetch.mock.calls[1][1].headers).toEqual({})
  })

  test('announces an ended session on a 401 UNAUTHENTICATED, but not on a wrong password', async () => {
    const heard = vi.fn()
    window.addEventListener(SESSION_EXPIRED, heard)
    reply(401, { ok: false, error: { code: 'INVALID_CREDENTIALS', message: 'Invalid email or password' } })
    await api('/api/auth/login', { method: 'POST', body: {} }).catch(() => {})
    expect(heard).not.toHaveBeenCalled()

    reply(401, { ok: false, error: { code: 'UNAUTHENTICATED', message: 'Please sign in first' } })
    await api('/api/orders').catch(() => {})
    expect(heard).toHaveBeenCalledTimes(1)
    window.removeEventListener(SESSION_EXPIRED, heard)
  })
})
