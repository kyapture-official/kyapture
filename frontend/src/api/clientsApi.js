// File Location: frontend/src/api/clientsApi.js

import api from './axiosInstance'

/**
 * WHAT: Public Client API Service Client
 * WHY:  Manages all public-facing, unauthenticated and token-authenticated
 *       endpoint queries for client gallery viewports. Deliberately isolated
 *       from the dashboard network layer so this module never has access to
 *       staff/photographer auth state.
 */

// ─────────────────────────────────────────────────────────────────────────────
// PRIVATE HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Asserts that `value` is a non-empty string. Throws a TypeError tagged with
 * `code: 'INVALID_ARGUMENT'` and `status: null`, matching the same shape
 * (`.status`, `.code`) that `normalizeError` produces for network/HTTP
 * failures — so any consumer doing uniform `error.status` checks gets a
 * consistent `null` rather than `undefined` regardless of which failure path
 * fired.
 */
function assertNonEmptyString(value, paramName) {
  if (typeof value !== 'string' || !value.trim()) {
    const err = new TypeError(`clientsApi: "${paramName}" is required and must be a non-empty string`)
    err.code = 'INVALID_ARGUMENT'
    err.status = null
    throw err
  }
}

/**
 * Builds the `/public/{username}/` profile resource path.
 */
function buildProfilePath(username) {
  assertNonEmptyString(username, 'username')
  return `/public/${encodeURIComponent(username.trim())}/`
}

/**
 * Builds the `/public/{username}/{slug}/` gallery resource path.
 */
function buildGalleryPath(username, slug) {
  assertNonEmptyString(username, 'username')
  assertNonEmptyString(slug, 'slug')
  return `/public/${encodeURIComponent(username.trim())}/${encodeURIComponent(slug.trim())}/`
}

/**
 * Builds the `/public/{username}/{slug}/verify-password/` action path.
 */
const buildVerifyPasswordPath = (username, slug) => {
  return `${buildGalleryPath(username, slug)}verify-password/`
}

/**
 * Matches abort/cancellation events across legacy and modern browser engines.
 */
function isCanceled(error) {
  return (
    error?.code === 'ERR_CANCELED' ||
    error?.name === 'CanceledError' ||
    error?.name === 'AbortError'
  )
}

/**
 * Converts raw network anomalies into standardized system Error payloads,
 * preventing field arrays from leaking as "[object Object]".
 * NOTE: Only reached for actual request/response failures — input validation
 * errors (see assertNonEmptyString) are thrown before any network call is
 * made and propagate as raw TypeErrors instead.
 *
 * NOTE: A backend-supplied data.error/data.message/data.detail string takes
 * precedence over authMessage/notFoundMessage on ANY status, including
 * 401/403/404. Confirm this is the intended UX — if backend error bodies
 * are written for developers rather than end users, this can leak internal
 * wording (e.g. "JWT signature invalid") in place of the curated copy.
 */
function normalizeError(error, { authMessage, notFoundMessage } = {}) {
  const status = error?.response?.status ?? null
  const data = error?.response?.data

  const fallback =
    status === 401 || status === 403
      ? authMessage || 'You are not authorized to view this content.'
      : status === 404
      ? notFoundMessage || 'This resource could not be found.'
      : status === 429
      ? 'Too many requests. Please wait a moment and try again.'
      : status === null
      ? 'Network error. Please check your connection and try again.'
      : 'Something went wrong. Please try again.'

  // Returns the trimmed value, not the raw original — a backend body with
  // stray leading/trailing whitespace must not leak into displayed UI text.
  const pick = (val) => (typeof val === 'string' && val.trim() ? val.trim() : null)
  const message = pick(data?.error) || pick(data?.message) || pick(data?.detail) || fallback

  const normalized = new Error(message)
  normalized.status = status
  normalized.code = data?.code ?? null
  normalized.cause = error
  return normalized
}

/**
 * Shared catch-block handler. Re-throws cancellations untouched; normalizes others.
 */
function handleRequestError(error, context) {
  if (isCanceled(error)) {
    throw error
  }
  throw normalizeError(error, context)
}

// ─────────────────────────────────────────────────────────────────────────────
// CLIENTS API EXPORTS
// ─────────────────────────────────────────────────────────────────────────────

export const clientsApi = {
  /**
   * Fetch a photographer's public profile and list of published galleries.
   * URI: GET /api/v1/public/{username}/
   *
   * @param {string} username - Photographer identifier.
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal] - Optional cancellation token.
   * @returns {Promise<{ profile: PhotographerProfile, galleries: Gallery[] }>}
   * @throws {TypeError} Rejects with `code: 'INVALID_ARGUMENT'`, `status: null` if `username` is missing/blank.
   */
  getPhotographerProfile: async (username, options = {}) => {
    // Assertions run synchronously before the try-catch block
    const path = buildProfilePath(username)
    // Tolerates explicit null being passed as options (e.g. from condition-checks), not just undefined
    const { signal } = options || {}
    try {
      const res = await api.get(path, { signal })
      return res.data
    } catch (error) {
      handleRequestError(error, {
        notFoundMessage: 'This photographer could not be found.',
      })
    }
  },

  /**
   * Fetch public gallery metadata (and photos, if accessible).
   * Supports both object-destructured and index-based polymorphic call signatures.
   *
   * @param {string} username - Photographer/subdomain identifier.
   * @param {string} slug - Unique gallery slug.
   * @param {string|Object} [accessTokenOrOptions] - Short-lived access token OR options object.
   * @param {Object} [options] - Remaining parameters (ignored if signature 2 is used).
   * @throws {TypeError} Rejects with `code: 'INVALID_ARGUMENT'`, `status: null` if `username`/`slug` are missing/blank.
   */
  getGallery: async (username, slug, accessTokenOrOptions = null, options = {}) => {
    // Assertions run synchronously before the try-catch block
    const path = buildGalleryPath(username, slug)

    let token = null
    let signal = null

    // Polymorphic Signature Resolver:
    //   Signature 1 (Destructured): (username, slug, { accessToken, signal })
    //   Signature 2 (Positional):   (username, slug, tokenString, { signal })
    if (accessTokenOrOptions && typeof accessTokenOrOptions === 'object') {
      token = accessTokenOrOptions.accessToken || accessTokenOrOptions.token
      signal = accessTokenOrOptions.signal
    } else {
      token = accessTokenOrOptions
      signal = options?.signal
    }

    const config = { signal }
    if (token) {
      config.headers = { Authorization: `Bearer ${token}` }
    }

    try {
      const res = await api.get(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  // Alias mapper to guarantee backward compatibility with legacy imports
  getPublicGallery: (...args) => clientsApi.getGallery(...args),

  /**
   * Verify a gallery's password and exchange it for a short-lived access token.
   * URI: POST /api/v1/public/{username}/{slug}/verify-password/
   *
   * @param {string} username - Photographer/subdomain identifier.
   * @param {string} slug - Unique gallery slug.
   * @param {string} password - Password entered by the visitor.
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   * @throws {TypeError} Rejects with `code: 'INVALID_ARGUMENT'`, `status: null` if any argument is missing/blank.
   */
  unlock: async (username, slug, password, options = {}) => {
    // Assertions run synchronously before the try-catch block
    const path = buildVerifyPasswordPath(username, slug)
    assertNonEmptyString(password, 'password')
    // Tolerates explicit null being passed as options (e.g. from condition-checks), not just undefined
    const { signal } = options || {}

    try {
      const res = await api.post(path, { password }, { signal })
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'Incorrect password. Please try again.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  // Alias mapper to guarantee backward compatibility with legacy calls
  verifyPassword: (...args) => clientsApi.unlock(...args),
}