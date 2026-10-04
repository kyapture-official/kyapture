// File Location: frontend/src/utils/appUrl.js
//
// The ONE place a client-facing gallery link is built. Nothing else in the app
// may assemble `origin + /g/...` by hand, and no port is ever hard-coded:
//
//   origin = VITE_PUBLIC_APP_URL (when it is set to a valid http(s) URL)
//            otherwise window.location.origin (whatever the app is served from:
//            localhost:3000 on docker, the Vite dev port on `npm run dev`, the
//            real domain in production)
//   path   = /g/{username}/{slug}  (path-based only — see docs/KYAPTURE_PRODUCT_DECISIONS.md #3-4)
//
// Why the server's `share_url` is NOT used: it is built from the backend's
// FRONTEND_URL setting, which defaults to the Vite dev port (localhost:5173).
// Under docker the app is served on localhost:3000, so that link was dead.
// The browser always knows the origin it is actually being served from.

/** Reduces a configured app URL to a bare `origin`, or '' when it is not a usable http(s) URL. */
export function normalizeAppOrigin(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const parsed = new URL(value.trim())
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return ''
    return parsed.origin
  } catch {
    return ''
  }
}

/**
 * The origin links are built on. `configured` / `locationOrigin` are injectable
 * so the rule can be unit-tested without a browser or Vite.
 */
export function resolveAppOrigin({
  configured = import.meta.env?.VITE_PUBLIC_APP_URL,
  locationOrigin = typeof window !== 'undefined' ? window.location.origin : '',
} = {}) {
  return normalizeAppOrigin(configured) || normalizeAppOrigin(locationOrigin)
}

/**
 * The public client link for a gallery: `{origin}/g/{username}/{slug}`.
 * Returns '' until both parts are known (e.g. the profile has not loaded yet),
 * so callers can disable their button instead of copying a broken link.
 * Carries no query string, hash, PIN or token — ever.
 */
export function buildGalleryLink(username, slug, options) {
  if (!username || !slug) return ''
  const origin = resolveAppOrigin(options)
  if (!origin) return ''
  return `${origin}/g/${encodeURIComponent(username)}/${encodeURIComponent(slug)}`
}
