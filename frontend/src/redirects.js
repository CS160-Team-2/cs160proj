// Pages that need a signed-in person; losing the session on one of these sends the customer to sign in.
const PROTECTED_PREFIXES = ['/checkout', '/orders', '/account', '/manager', '/inventory', '/delivery']

// True when the path is one of the pages that need a sign-in.
export const isProtectedPath = (pathname) =>
  PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))

// Only lets a ?next= value through when it is a path on this site, so a sign-in link cannot send people elsewhere.
export const safeNext = (value) => {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/'
  return value
}

// The sign-in page address that brings the customer back to a path afterwards.
export const loginUrl = (pathname, expired = false) =>
  `/login?next=${encodeURIComponent(pathname)}${expired ? '&expired=1' : ''}`
