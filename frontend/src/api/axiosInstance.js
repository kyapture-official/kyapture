// File Location: frontend/src/api/axiosInstance.js

import axios from 'axios'

// ── BASE CONFIGURATION & PATH NORMALIZATION ─────────────────────────────────
const rawBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
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

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (!originalRequest) return Promise.reject(error)

    const isAuthRoute =
      originalRequest.url?.includes('/auth/token/refresh/') ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/')

    if (error.response?.status === 401 && !isAuthRoute && !originalRequest._retry) {
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