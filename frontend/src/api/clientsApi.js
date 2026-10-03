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
 * Builds an anchor-safe public API URL rather than an axios request. The API
 * base matches axiosInstance so this works in local proxy and deployed API
 * base-url configurations alike.
 */
function buildPublicApiUrl(path) {
  const apiBaseUrl = (
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.VITE_API_URL ||
    '/api/v1'
  ).replace(/\/+$/, '')
  return `${apiBaseUrl}${path}`
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
    const { signal, resolution, pin, setId } = options || {}

    try {
      // ENFORCE: responseType: 'blob' is mandatory in Axios to process
      // binary ZIP streaming chunks safely without corrupting them into strings.
      const res = await api.post(
        path,
        {
          email,
          token,
          asset_ids: assetIds,
          resolution: resolution || undefined,
          pin: pin || undefined,
          set_id: setId || undefined,
        },
        { signal, responseType: 'blob' }
      )
      return res.data
    } catch (error) {
      // responseType: 'blob' means an error JSON body (e.g. pin_required/
      // invalid_pin) arrives as a Blob, not parsed JSON — normalizeError()
      // above only reads error?.response?.data as if it were already an
      // object, so PIN errors need their own decode step here.
      if (isCanceled(error)) throw error
      if (error?.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text()
          const parsed = JSON.parse(text)
          const normalized = new Error(parsed.error || parsed.detail || 'Download request failed.')
          normalized.status = error.response.status
          normalized.code = parsed.code ?? null
          normalized.cause = error
          throw normalized
        } catch (parseErr) {
          if (parseErr instanceof Error && parseErr.status !== undefined) throw parseErr
          // Fall through to generic normalization if the blob wasn't JSON.
        }
      }
      handleRequestError(error, {
        authMessage: 'An active unlocked session is required to download this gallery.',
        notFoundMessage: 'This gallery could not be found.',
      })
    }
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

  /**
   * Builds the direct streaming ZIP link for an entire gallery, or one
   * photo set of it. This is kept as a URL helper so the browser, not
   * axios, owns a potentially large file.
   *
   * @param {Object} [opts]
   * @param {string} [opts.token] - gallery unlock token (protected galleries)
   * @param {string} [opts.downloadToken] - from requestDownloadAccess()
   * @param {string} [opts.resolution] - 'web' | 'download' | 'original'
   * @param {string} [opts.setId] - limit the archive to this photo set
   */
  buildGalleryDownloadAllHref: (username, slug, opts = {}) => {
    const params = new URLSearchParams()
    if (opts.token) params.set('token', opts.token)
    if (opts.downloadToken) params.set('download_token', opts.downloadToken)
    if (opts.resolution) params.set('resolution', opts.resolution)
    if (opts.setId) params.set('set', opts.setId)
    const query = params.toString()
    const path = `${buildGalleryPath(username, slug)}download-all/`
    return `${buildPublicApiUrl(path)}${query ? `?${query}` : ''}`
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
