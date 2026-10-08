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

// 7G (reviewer 7R-2 R5): a tab that waited for the lock reuses the refresh another
// tab just made instead of rotating the token again. Every successful refresh
// stores when it finished (shared by all tabs through localStorage); a request
// SENT before that moment carried the old access cookie, and the cookie jar now
// holds a new one, so retrying it is enough.
export const REFRESHED_AT_KEY = 'kyapture-token-refreshed-at'

function readRefreshedAt(storage) {
  try { return Number(storage?.getItem(REFRESHED_AT_KEY)) || 0 } catch { return 0 }
}

function writeRefreshedAt(storage, at) {
  try { storage?.setItem(REFRESHED_AT_KEY, String(at)) } catch { /* private mode: the next tab just refreshes */ }
}

/**
 * Runs `refresh` under the cross-tab lock unless a refresh finished after `sentAt`
 * (when the failed request was sent). Resolves 'refreshed' or 'reused'.
 */
export function refreshOnce(sentAt, refresh, {
  locks = globalThis.navigator?.locks,
  storage = globalThis.localStorage,
  now = () => Date.now(),
} = {}) {
  return withRefreshLock(async () => {
    if (sentAt && readRefreshedAt(storage) > sentAt) return 'reused'
    await refresh()
    writeRefreshedAt(storage, now())
    return 'refreshed'
  }, locks)
}
