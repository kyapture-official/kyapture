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
 * Asserts that `value` is a non-empty string.
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
 * Builds the `/public/{username}/{slug}/unlock/` action path.
 */
const buildVerifyPasswordPath = (username, slug) => {
  // Fixed: Updated verify path from 'verify-password/' to 'unlock/' to match our certified backend views
  return `${buildGalleryPath(username, slug)}unlock/`
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
 * Converts raw network anomalies into standardized system Error payloads.
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
   */
  getPhotographerProfile: async (username, options = {}) => {
    const path = buildProfilePath(username)
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
   * @param {Object} [options] - Remaining parameters.
   */
  getGallery: async (username, slug, accessTokenOrOptions = null, options = {}) => {
    const path = buildGalleryPath(username, slug)

    let token = null
    let signal = null

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
   * URI: POST /api/v1/public/{username}/{slug}/unlock/
   *
   * @param {string} username - Photographer/subdomain identifier.
   * @param {string} slug - Unique gallery slug.
   * @param {string} password - Password entered by the visitor.
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   */
  unlock: async (username, slug, password, options = {}) => {
    const path = buildVerifyPasswordPath(username, slug)
    assertNonEmptyString(password, 'password')
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

  /**
   * Request a secure, memory-safe ZIP archive of the gallery's high-res original assets.
   * URI: POST /api/v1/public/{username}/{slug}/download/
   *
   * @param {string} username - Photographer/subdomain identifier.
   * @param {string} slug - Unique gallery slug.
   * @param {string} email - Guest client's email address (for auditing/lead capture).
   * @param {string} [token] - Optional guest session access token (if password-protected).
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<Blob>}
   */
  requestDownload: async (username, slug, email, token = null, assetIds = [], options = {}) => {
    const path = `${buildGalleryPath(username, slug)}download/`
    assertNonEmptyString(email, 'email')
    const { signal } = options || {}

    try {
      // ENFORCE: responseType: 'blob' is mandatory in Axios to process
      // binary ZIP streaming chunks safely without corrupting them into strings.
      const res = await api.post(
        path,
        { email, token, asset_ids: assetIds },
        { signal, responseType: 'blob' }
      )
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to download this gallery.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },
}