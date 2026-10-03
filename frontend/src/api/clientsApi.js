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
   * Fetch a subsequent page of a gallery's READY photos/videos.
   * URI: GET /api/v1/public/{username}/{slug}/photos/?page=N
   *
   * WHY (Phase 2, large-gallery performance): getGallery() above only
   * ever returns the FIRST page of assets (see the gallery payload's
   * `photos_has_more` / `photos_page_size` fields) — a gallery with
   * hundreds or thousands of photos is never sent as one giant array.
   * The client gallery page calls this to fetch page 2, 3, ... as the
   * visitor scrolls or clicks "load more", using the same password-
   * session token as getGallery() for protected galleries.
   *
   * @param {string} username
   * @param {string} slug
   * @param {number} page - 1-indexed page number (2, 3, ...).
   * @param {string} [token] - Session access token for protected galleries.
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<{ count: number, next: string|null, previous: string|null, results: MediaAsset[] }>}
   */
  getGalleryPhotos: async (username, slug, page, token = null, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}photos/`
    const { signal } = options || {}

    const config = { signal, params: { page } }
    if (token) {
      config.headers = { Authorization: `Bearer ${token}` }
    }

    try {
      const res = await api.get(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to view more photos.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

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
   * Step two of a gallery / set Download: ask the server to PREPARE the ZIP.
   * URI: POST /api/v1/public/{username}/{slug}/download/
   *
   * Nothing is streamed. The server re-checks every gate and answers 202 with
   * a job id; poll getDownloadJob() until it is ready.
   *
   * @param {Object} opts
   * @param {string} opts.downloadToken - from requestDownloadAccess() (omit only when the gallery needs none)
   * @param {string} [opts.token] - gallery unlock token (protected galleries)
   * @param {string} [opts.resolution] - 'web' | 'download'
   * @param {string} [opts.setId] - limit the ZIP to this photo set
   * @returns {Promise<{ job_id: string, state: string, status_url: string }>}
   */
  prepareGalleryDownload: async (username, slug, opts = {}) => {
    const path = `${buildGalleryPath(username, slug)}download/`
    const { downloadToken, token, resolution, setId, signal } = opts

    const body = {}
    if (downloadToken) body.download_token = downloadToken
    if (resolution) body.resolution = resolution
    if (setId) body.set_id = setId

    const config = { signal }
    if (token) config.headers = { Authorization: `Bearer ${token}` }
    if (token) body.token = token

    try {
      const res = await api.post(path, body, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'Unable to start this download.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  /**
   * Status of a prepared download.
   * URI: GET /api/v1/public/{username}/{slug}/download-jobs/{jobId}/
   *
   * Each ready file carries a signed URL that is only good for a few minutes,
   * so fetch the status again right before starting the browser download
   * instead of keeping an old URL around.
   *
   * @returns {Promise<{ state: 'preparing'|'ready'|'failed', files: Array<{name: string, size_bytes: number, url: string}>, error?: string, code?: string }>}
   */
  getDownloadJob: async (username, slug, jobId, opts = {}) => {
    assertNonEmptyString(jobId, 'jobId')
    const path = `${buildGalleryPath(username, slug)}download-jobs/${encodeURIComponent(jobId)}/`
    const { downloadToken, token, signal } = opts

    const params = {}
    if (downloadToken) params.download_token = downloadToken
    const config = { signal, params }
    if (token) config.headers = { Authorization: `Bearer ${token}` }

    try {
      const res = await api.get(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'Your download session has expired. Please try again.',
        notFoundMessage: 'This download could not be found.',
      })
    }
  },

  /**
   * The browser-download link for one ready file: the signed URL from
   * getDownloadJob(), plus the gallery unlock token when the gallery has one
   * (an anchor cannot send an Authorization header).
   */
  buildJobFileHref: (fileUrl, opts = {}) => {
    if (!fileUrl) return null
    return opts.token
      ? `${fileUrl}${fileUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(opts.token)}`
      : fileUrl
  },

  /**
   * Step one of an explicit Download: ask the server to authorize it.
   * URI: POST /api/v1/public/{username}/{slug}/download-access/
   *
   * Called only when the client chooses Download — never while opening or
   * browsing a gallery. The server verifies the download PIN (when the
   * gallery has one) and the email, and returns a short-lived signed
   * `download_token` that authorizes the actual file/ZIP requests, so
   * email/PIN are asked once per session rather than once per photo.
   *
   * Rejects with an Error whose `.code` is one of: pin_required,
   * invalid_pin, email_required, invalid_email, session_required,
   * downloads_disabled (see download_access.py).
   *
   * @param {string} username
   * @param {string} slug
   * @param {Object} credentials
   * @param {string} [credentials.email]
   * @param {string} [credentials.pin]
   * @param {string} [credentials.token] - gallery unlock token (protected galleries)
   * @param {Object} [options]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<{ download_token: string, expires_in: number, email: string, pin_verified: boolean }>}
   */
  requestDownloadAccess: async (username, slug, credentials = {}, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}download-access/`
    const { email, pin, token } = credentials || {}
    const { signal } = options || {}

    const body = {}
    if (email) body.email = email
    if (pin) body.pin = pin

    const config = { signal }
    if (token) config.headers = { Authorization: `Bearer ${token}` }

    try {
      const res = await api.post(path, body, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'Unable to authorize this download.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  /**
   * Builds the direct <a href> for a single photo/video download. Never
   * fetches — PublicPhotoDownloadView is a plain GET meant to be used as a
   * real anchor href (forces a "Save As"). The download PIN never goes in
   * the URL: the client first earns a `downloadToken` via
   * requestDownloadAccess().
   *
   * @param {string} downloadUrl - photo.download_url from the API (already token-less)
   * @param {Object} [opts]
   * @param {string} [opts.token] - gallery unlock token (protected galleries)
   * @param {string} [opts.downloadToken] - from requestDownloadAccess()
   * @param {string} [opts.resolution] - 'web' | 'download' | 'original'
   */
  buildPhotoDownloadHref: (downloadUrl, opts = {}) => {
    if (!downloadUrl) return null
    const params = new URLSearchParams()
    if (opts.token) params.set('token', opts.token)
    if (opts.downloadToken) params.set('download_token', opts.downloadToken)
    if (opts.resolution) params.set('resolution', opts.resolution)
    const qs = params.toString()
    return qs ? `${downloadUrl}${downloadUrl.includes('?') ? '&' : '?'}${qs}` : downloadUrl
  },

  // ─────────────────────────────────────────────────────────────────────────
  // PHOTO SETS (Phase 3) — client-facing set tabs
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Fetch a page of a gallery's READY photos, optionally scoped to one
   * PhotoSet tab. Reuses getGalleryPhotos' pagination envelope.
   *
   * @param {string} username
   * @param {string} slug
   * @param {number} page
   * @param {string|null} setId - PhotoSet id, or null/undefined for "All"
   * @param {string} [token]
   * @param {Object} [options]
   */
  getGalleryPhotosBySet: async (username, slug, page, setId = null, token = null, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}photos/`
    const { signal } = options || {}
    const params = { page }
    if (setId) params.set = setId

    const config = { signal, params }
    if (token) config.headers = { Authorization: `Bearer ${token}` }

    try {
      const res = await api.get(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to view more photos.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  // ─────────────────────────────────────────────────────────────────────────
  // FAVORITES (Phase 3)
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Batch-fetch every media_asset id this client has favorited in this
   * gallery — ONE request restores heart-icon state for the whole grid,
   * instead of one request per photo.
   *
   * @param {string} username
   * @param {string} slug
   * @param {Object} identity - { clientUid } for open galleries, or { token } for protected ones
   */
  getFavorites: async (username, slug, identity = {}, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}favorites/`
    const { signal } = options || {}
    const params = {}
    if (identity.clientUid) params.client_uid = identity.clientUid

    const config = { signal, params }
    if (identity.token) config.headers = { Authorization: `Bearer ${identity.token}` }

    try {
      const res = await api.get(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to view favorites.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
  },

  /**
   * Favorite one photo. Idempotent — favoriting twice is a harmless no-op.
   *
   * @param {string} username
   * @param {string} slug
   * @param {string} mediaAssetId
   * @param {Object} identity - { clientUid } for open galleries, or { token } for protected ones
   */
  addFavorite: async (username, slug, mediaAssetId, identity = {}, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}favorites/`
    assertNonEmptyString(mediaAssetId, 'mediaAssetId')
    const { signal } = options || {}

    const body = { media_asset_id: mediaAssetId }
    if (identity.clientUid) body.client_uid = identity.clientUid

    const config = { signal }
    if (identity.token) config.headers = { Authorization: `Bearer ${identity.token}` }

    try {
      const res = await api.post(path, body, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to favorite photos.',
        notFoundMessage: 'This photo could not be found.',
      })
    }
  },

  /**
   * Unfavorite one photo. Idempotent — unfavoriting something never
   * favorited is a harmless no-op.
   */
  removeFavorite: async (username, slug, mediaAssetId, identity = {}, options = {}) => {
    const path = `${buildGalleryPath(username, slug)}favorites/`
    assertNonEmptyString(mediaAssetId, 'mediaAssetId')
    const { signal } = options || {}

    const body = { media_asset_id: mediaAssetId }
    if (identity.clientUid) body.client_uid = identity.clientUid

    const config = { signal, data: body }
    if (identity.token) config.headers = { Authorization: `Bearer ${identity.token}` }

    try {
      const res = await api.delete(path, config)
      return res.data
    } catch (error) {
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to favorite photos.',
        notFoundMessage: 'This photo could not be found.',
      })
    }
  },
}
