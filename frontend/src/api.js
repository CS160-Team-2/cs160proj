// One place for every call to the OFS backend.
//
// The backend runs on its own port in development, so requests go to
// VITE_API_BASE (default http://localhost:5001). `credentials: 'include'`
// sends the sign-in cookie along, which is how the backend knows whose
// cart this is.
//
// Every backend reply is {ok: true, ...} or {ok: false, error: {code,
// message}}. On an error this throws, and the thrown error carries the
// backend's message (written for customers) and code.

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5001'

export class ApiError extends Error {
    constructor(message, code, status) {
        super(message)
        this.code = code
        this.status = status
    }
}

export async function api(path, { method = 'GET', body } = {}) {
    let response
    try {
        response = await fetch(`${API_BASE}${path}`, {
            method,
            credentials: 'include',
            headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        })
    } catch {
        throw new ApiError('Cannot reach the store right now. Is the backend running?', 'NETWORK', 0)
    }

    const data = await response.json().catch(() => ({}))
    if (!response.ok || data.ok === false) {
        const error = data.error || {}
        throw new ApiError(error.message || 'Something went wrong', error.code || 'ERROR', response.status)
    }
    return data
}
