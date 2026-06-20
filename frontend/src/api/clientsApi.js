import api from './axiosInstance'

/**
 * WHAT: Public Client API Service
 * WHY:  Manages unauthenticated and token-authenticated endpoint queries for
 *       client galleries. Deliberately isolated from the dashboard network
 *       layer so this module never has access to staff/photographer auth state.
 *
 * UNIFIED CLIENT API DATA SHAPES:
 *   getPublicGallery()  → { is_protected: boolean, gallery_title: string, photos?: Photo[] }
 *   verifyPassword()    → { is_protected: false, gallery_title: string, photos: Photo[], access_token: string }
 *
 * PHOTO OBJECT INTERFACE:
 *   {
 *     id:            string (UUID),
 *     image_url:     string,
 *     original_name: string
 *   }
 *
 * USAGE:
 *   const gallery = await clientsApi.getPublicGallery(username, slug)
 *   if (gallery.is_protected) {
 *     const verified = await clientsApi.verifyPassword(username, slug, password)
 *     sessionStorage.setItem(`gallery_token:${username}:${slug}`, verified.access_token)
 *   }
 *
 *   // On a return visit, pass the saved token to skip the password prompt:
 *   const token = sessionStorage.getItem(`gallery_token:${username}:${slug}`)
 *   const gallery = await clientsApi.getPublicGallery(username, slug, { accessToken: token })
 */

// ─────────────────────────────────────────────────────────────────────────────
// PRIVATE HELPERS
// Plain functions invoked on every call — no memoization or module-load
// caching happens here, by design. Each call gets fresh validation.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Builds the `/public/{username}/{slug}/` resource path.
 * Throws early instead of silently producing `/public/undefined/undefined/`
 * when a caller forgets to pass an identifier.
 */
function buildGalleryPath(username, slug) {
  if (typeof username !== 'string' || !username.trim()) {
    throw new TypeError('clientsApi: "username" is required and must be a non-empty string')
  }
  if (typeof slug !== 'string' || !slug.trim()) {
    throw new TypeError('clientsApi: "slug" is required and must be a non-empty string')
  }
  return `/public/${encodeURIComponent(username.trim())}/${encodeURIComponent(slug.trim())}/`
}

/**
 * Converts an Axios error into a normalized Error object so UI code never
 * has to parse nested `error.response.data` objects directly.
 *
 * Checks a few common backend error-message keys, in priority order:
 *   1. `error`  — custom non-field exception key
 *   2. `message`
 *   3. `detail` — Django REST Framework's default key for built-in
 *                 exceptions (PermissionDenied, Throttled, NotFound, etc.)
 * Confirm against your actual backend response shape and adjust this list
 * if needed — it's deliberately additive, so it's safe to keep all three.
 */
function normalizeError(error) {
  const status = error?.response?.status ?? null
  const data = error?.response?.data

  const fallback =
    status === 401 || status === 403
      ? 'Incorrect password. Please try again.'
      : status === 404
      ? 'This gallery could not be found.'
      : 'Something went wrong while loading this gallery. Please try again.'

  const normalized = new Error(data?.error || data?.message || data?.detail || fallback)
  normalized.status = status
  normalized.code = data?.code ?? null
  normalized.cause = error
  return normalized
}

// ─────────────────────────────────────────────────────────────────────────────
// CLIENTS API EXPORTS
// ─────────────────────────────────────────────────────────────────────────────

export const clientsApi = {
  /**
   * Fetch public gallery metadata (and photos, if accessible).
   * URI: GET /api/v1/public/{username}/{slug}/
   *
   * @param {string} username - Photographer/subdomain identifier.
   * @param {string} slug - Unique gallery slug.
   * @param {Object} [options]
   * @param {string} [options.accessToken] - Token previously returned by verifyPassword.
   * @param {AbortSignal} [options.signal] - Lets callers cancel pending requests on unmount.
   * @returns {Promise<Object>} PublicGalleryResponse
   */
  getPublicGallery: (username, slug, { accessToken, signal } = {}) => {
    const path = buildGalleryPath(username, slug)
    const config = { signal }

    if (accessToken) {
      config.headers = { Authorization: `Bearer ${accessToken}` }
    }

    return api
      .get(path, config)
      .then((res) => res.data)
      .catch((error) => {
        throw normalizeError(error)
      })
  },

  /**
   * Verify a gallery's password.
   * URI: POST /api/v1/public/{username}/{slug}/verify-password/
   *
   * @param {string} username
   * @param {string} slug
   * @param {string} password - Client-input security string.
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<Object>} VerifyPasswordResponse
   */
  verifyPassword: (username, slug, password, { signal } = {}) => {
    const path = buildGalleryPath(username, slug)

    if (typeof password !== 'string' || !password.trim()) {
      const err = new Error('Please enter a password.')
      err.status = 400
      err.code = 'EMPTY_PASSWORD'
      return Promise.reject(err)
    }

    return api
      .post(`${path}verify-password/`, { password }, { signal })
      .then((res) => res.data)
      .catch((error) => {
        throw normalizeError(error)
      })
  },
}