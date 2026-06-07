import axios from 'axios'

// ─────────────────────────────────────────────────────────────────────────────
// BASE CONFIGURATION & PATH NORMALIZATION
// ─────────────────────────────────────────────────────────────────────────────

// Strip ALL trailing slashes (not just one) to prevent Django/Nginx
// double-slash 301 redirects that silently drop POST bodies.
const rawBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const cleanBaseURL = rawBaseURL.replace(/\/+$/, '')

const api = axios.create({
  baseURL: cleanBaseURL,
  headers: { 'Content-Type': 'application/json' },
})

// Refresh-cycle state — module-level to survive across interceptor calls
let isRefreshing = false
let failedQueue = []

/**
 * WHAT: Process Queue Handler
 * WHY:  Resolves or rejects all requests placed on hold during a silent
 *       token-refresh cycle, then flushes the queue.
 */
const processQueue = (error, token = null) => {
  failedQueue.forEach((promise) => {
    error ? promise.reject(error) : promise.resolve(token)
  })
  failedQueue = []
}

// ─────────────────────────────────────────────────────────────────────────────
// REQUEST INTERCEPTOR
// WHY: Dynamically injects the current access token on every outgoing request.
//      Reading directly from localStorage (rather than importing the store)
//      eliminates the circular-import risk: axiosInstance ← authStore ← axiosInstance.
// ─────────────────────────────────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ─────────────────────────────────────────────────────────────────────────────
// RESPONSE INTERCEPTOR
// WHY: Intercepts 401 failures, runs a silent refresh cycle, replays queued
//      requests with the new token, and dispatches a global logout event on
//      absolute session failure.
// ─────────────────────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (!originalRequest) {
      return Promise.reject(error)
    }

    // Do not attempt a refresh on auth-related routes — doing so would create
    // an infinite 401 → refresh → 401 loop on the refresh endpoint itself.
    const isAuthRoute =
      originalRequest.url?.includes('/auth/token/refresh/') ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/')

    if (error.response?.status === 401 && !isAuthRoute && !originalRequest._retry) {

      // ── Queue path: a refresh is already in-flight ──────────────────────
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            // Mark as retried to block nested refresh loops if this retried
            // request itself receives another 401.
            originalRequest._retry = true
            originalRequest.headers = originalRequest.headers || {}
            originalRequest.headers.Authorization = `Bearer ${token}`
            return api(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      // ── Refresh path: this request initiates the refresh cycle ──────────
      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        // Release lock and drain queue defensively before bailing.
        isRefreshing = false
        processQueue(error, null)
        triggerGlobalLogout()
        return Promise.reject(error)
      }

      try {
        // Use raw axios (not the api instance) to prevent this call from
        // being intercepted and re-queued on failure.
        // cleanBaseURL guarantees no double-slash in the final URL.
        // 10-second timeout prevents an unresponsive server from blocking
        // the entire queue indefinitely.
        const refreshURL = `${cleanBaseURL}/auth/token/refresh/`
        const { data } = await axios.post(
          refreshURL,
          { refresh: refreshToken },
          { timeout: 10_000 }
        )

        const newAccessToken = data.access
        localStorage.setItem('access_token', newAccessToken)

        // The request interceptor is the single source of truth for the
        // Authorization header — no api.defaults mutation needed here.
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`

        // Release the lock BEFORE draining the queue so queued callbacks
        // always observe a consistent, unlocked state.
        isRefreshing = false
        processQueue(null, newAccessToken)

        return api(originalRequest)

      } catch (refreshError) {
        // Consistent order: clear lock → drain queue → logout.
        isRefreshing = false
        processQueue(refreshError, null)
        triggerGlobalLogout()
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL LOGOUT DISPATCHER
// WHY: Clears credentials and notifies the app of session expiry without
//      importing authStore (which would re-introduce the circular dependency).
//      typeof window guard keeps this module SSR-safe.
// ─────────────────────────────────────────────────────────────────────────────
function triggerGlobalLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth-session-expired'))
  }
}

export default api
