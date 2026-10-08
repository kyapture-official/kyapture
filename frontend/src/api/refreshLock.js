// File Location: frontend/src/api/refreshLock.js
//
// 7F (reviewer F7): one token refresh at a time across ALL tabs of this origin.
//
// The refresh token rotates: a refresh blacklists the token it was sent with and
// sets a new refresh cookie. The cookie jar is shared by every tab, but two tabs
// whose access token expired at the same moment used to send their refresh
// requests at once, both carrying the OLD refresh cookie: the second got 401 and
// signed every tab out. Held under a Web Lock, the second tab's refresh starts
// only after the first one's response has set the new cookie, so it succeeds.
// Within one tab, axiosInstance.js already queues requests behind one refresh.
//
// Without the Web Locks API (very old browsers, non-secure contexts) the refresh
// simply runs unlocked, as it did before.

export const REFRESH_LOCK_NAME = 'kyapture-token-refresh'

export function withRefreshLock(fn, locks = globalThis.navigator?.locks) {
  if (!locks || typeof locks.request !== 'function') return fn()
  return locks.request(REFRESH_LOCK_NAME, { mode: 'exclusive' }, () => fn())
}
