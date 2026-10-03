// File Location: frontend/src/api/axiosInstance.js

import axios from 'axios'

// ── BASE CONFIGURATION & PATH NORMALIZATION ─────────────────────────────────
// Checks VITE_API_BASE_URL first (correct), falls back to legacy VITE_API_URL
// for backward compatibility with older .env files.
const rawBaseURL =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  '/api/v1'
// Normalize the base URL by stripping trailing slashes.
// Relative paths must always start with a leading slash and end with a trailing
// slash (e.g. '/auth/login/') to prevent double-slashes while complying with
// Django REST Framework's strict trailing slash routing expectations.
const cleanBaseURL = rawBaseURL.replace(/\/+$/, '')

// Defensive path join for the one manual URL built below (the refresh call
// intentionally bypasses the `api` instance, so it doesn't get axios's own
// baseURL/url merging).
const joinPath = (path) => `${cleanBaseURL}${path.startsWith('/') ? path : `/${path}`}`

/**
 * WHAT: Centralized Axios Instance
 * WHY:  Abstracts the traditional local-storage JWT Bearer session transport
 *       used prior to the cookie migration rollout.
 */
const api = axios.create({
  baseURL: cleanBaseURL,
  withCredentials: true,    // CRITICAL: Forces browser to save/transmit secure cookies on
  timeout: 15000, // 15-second network timeout boundary
})

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

api.interceptors.request.use(
  (config) => {
    const method = (config.method || 'get').toUpperCase()
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrfToken = getCsrfToken()
      if (csrfToken) {
        config.headers = config.headers || {}
        config.headers['X-CSRFToken'] = csrfToken
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

let isRefreshing = false
let failedQueue = []

const processQueue = (error) => {
  failedQueue.forEach(({ resolve, reject }) => {
    error ? reject(error) : resolve()
  })
  failedQueue = []
}

const isHtmlErrorResponse = (response) => {
  const contentType = String(response?.headers?.['content-type'] || '')
  const body = response?.data
  return typeof body === 'string' && (
    contentType.includes('text/html') ||
    /^\s*<!doctype html/i.test(body) ||
    /^\s*<html[\s>]/i.test(body)
  )
}

// A development Django debug page is never a useful application error. Keep
// callers on the normal API-error path even if an upstream server misbehaves.
const normalizeUnexpectedErrorPayload = (error) => {
  if (isHtmlErrorResponse(error?.response)) {
    error.response.data = {
      error: 'The server could not complete that request. Please try again.',
      code: 'unexpected_server_error',
    }
  }
  return error
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    normalizeUnexpectedErrorPayload(error)
    // ── CONNECTION REFUSED: backend not reachable ──────────────────────────
    // Axios sets code === 'ERR_NETWORK' and message includes
    // 'ERR_CONNECTION_REFUSED' when the proxy target (localhost:8000) is down.
    if (!error.response && error.code === 'ERR_NETWORK') {
      console.error(
        '[kyapture] Backend unreachable. Ensure the Django server is running at the configured API URL.\n' +
        '  Start it with: python backend/manage.py runserver\n' +
        '  Current API base URL:', cleanBaseURL,
      )
    }

    const originalRequest = error.config
    if (!originalRequest) return Promise.reject(error)

    const isAuthRoute =
      originalRequest.url?.includes('/auth/token/refresh/') ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/')

    // Guest/public gallery requests (clientsApi.js) share this same axios
    // instance with the photographer-authenticated API modules
    // (galleriesApi.js, photosApi.js, authApi.js, ...), but a guest has no
    // access/refresh cookie pair at all — a 401 from a public gallery
    // route (wrong/missing unlock token, gallery not accessible) is an
    // ordinary, expected response for that guest, never a signal that a
    // photographer's session needs refreshing or ending. Without this
    // check, a guest 401 here would attempt a refresh using whatever
    // cookies happen to be in the browser and, on failure, log out any
    // photographer session active in that same browser/tab. Public gallery
    // error handling (404/401/expired/password) is instead handled by the
    // calling code in clientsApi.js / ClientGalleryPage.jsx.
    const isPublicRoute = originalRequest.url?.includes('/public/')

    if (error.response?.status === 401 && !isAuthRoute && !isPublicRoute && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(() => {
          originalRequest._retry = true
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        // No body needed — the refresh_token cookie rides along automatically
        // because withCredentials is true. Uses bare `axios`, not `api`, so
        // this call never re-enters these same interceptors.
        await axios.post(joinPath('/auth/token/refresh/'), {}, {
          withCredentials: true,
          timeout: 10000,
        })
        isRefreshing = false
        processQueue(null)
        return api(originalRequest)
      } catch (refreshError) {
        isRefreshing = false
        processQueue(refreshError)
        triggerGlobalLogout()
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

function triggerGlobalLogout() {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    if (persisted) {
      const parsed = JSON.parse(persisted)
      if (parsed?.state) {
        parsed.state.user = null
        parsed.state.isAuthenticated = false
        localStorage.setItem('kyapture-auth', JSON.stringify(parsed))
      }
    }
  } catch {}

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth-session-expired'))
  }
}

export default api
