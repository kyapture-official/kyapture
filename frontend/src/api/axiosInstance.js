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
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000, // 15-second network timeout boundary
})

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((promise) => {
    error ? promise.reject(error) : promise.resolve(token)
  })
  failedQueue = []
}

// ── TOKEN STORAGE HELPERS ───────────────────────────────────────────────────
// Reads and writes directly from Zustand's persisted 'kyapture-auth' key

const getAccessToken = () => {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    return persisted ? JSON.parse(persisted)?.state?.accessToken : null
  } catch {
    return null
  }
}

const getRefreshToken = () => {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    return persisted ? JSON.parse(persisted)?.state?.refreshToken : null
  } catch {
    return null
  }
}

// Persists a refreshed access token, and the refresh token too if the backend
// rotates it (SIMPLE_JWT ROTATE_REFRESH_TOKENS). If no rotated refresh token
// comes back, the existing one in storage is left alone.
const setTokens = (accessToken, refreshToken) => {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    if (persisted) {
      const parsed = JSON.parse(persisted)
      if (parsed?.state) {
        parsed.state.accessToken = accessToken
        if (refreshToken) {
          parsed.state.refreshToken = refreshToken
        }
        localStorage.setItem('kyapture-auth', JSON.stringify(parsed))
      }
    }
  } catch {
    // Fail silently in non-browser environments
  }
}

// ── REQUEST INTERCEPTOR ─────────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken()
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ── RESPONSE INTERCEPTOR ────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (!originalRequest) {
      return Promise.reject(error)
    }

    // Exclude authentication routes from interception to prevent infinite loop races
    const isAuthRoute =
      originalRequest.url?.includes('/auth/token/refresh/') ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/')

    if (error.response?.status === 401 && !isAuthRoute && !originalRequest._retry) {

      // Trailing-edge race: this request was sent before another one triggered
      // + finished a refresh, so the token it carries is now stale. Retry
      // once with whatever's current instead of queueing behind, or kicking
      // off, a second unnecessary refresh.
      const currentAccessToken = getAccessToken()
      const sentWithStaleToken =
        currentAccessToken &&
        originalRequest.headers?.Authorization !== `Bearer ${currentAccessToken}`

      if (sentWithStaleToken) {
        originalRequest._retry = true
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${currentAccessToken}`
        return api(originalRequest)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalRequest._retry = true
            originalRequest.headers = originalRequest.headers || {}
            originalRequest.headers.Authorization = `Bearer ${token}`
            return api(originalRequest)
          })
          .catch((err) => Promise.reject(err))
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = getRefreshToken()
      if (!refreshToken) {
        isRefreshing = false
        processQueue(error, null)
        triggerGlobalLogout()
        return Promise.reject(error)
      }

      try {
        // Deliberately calls the bare `axios` client rather than `api`: this
        // request must never re-enter these interceptors, or a failed
        // refresh could recurse into itself.
        const refreshURL = joinPath('/auth/token/refresh/')

        const { data } = await axios.post(
          refreshURL,
          { refresh: refreshToken },
          { timeout: 10000 }
        )

        setTokens(data.access, data.refresh)

        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${data.access}`

        isRefreshing = false
        processQueue(null, data.access)

        return api(originalRequest)

      } catch (refreshError) {
        isRefreshing = false
        processQueue(refreshError, null)
        triggerGlobalLogout()
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

// ── GLOBAL LOGOUT DISPATCHER ─────────────────────────────────────────────────
// Clears local security parameters (accessToken, refreshToken, user) and
// notifies the app via 'auth-session-expired'.
//
// Guard: if there's nothing left to clear, return without dispatching again.
// Without this, any listener that reacts to 'auth-session-expired' by
// re-checking auth (e.g. re-fetching /me/) 401s again with no refresh token,
// calls this function again, and the event fires again — forever.
//
// This only clears the *persisted* copy in localStorage. Zustand's in-memory
// state is a separate copy that components actually read from, and writing
// to localStorage doesn't touch it. Whatever listens for
// 'auth-session-expired' — almost certainly authStore.js — needs to clear its
// own in-memory accessToken/refreshToken/user in that same listener, or it
// keeps acting on the stale in-memory token and reproduces the same loop one
// layer up. Worth confirming that's actually happening there.
function triggerGlobalLogout() {
  let alreadyLoggedOut = true

  try {
    const persisted = localStorage.getItem('kyapture-auth')
    if (persisted) {
      const parsed = JSON.parse(persisted)
      if (parsed?.state && (parsed.state.accessToken || parsed.state.refreshToken)) {
        alreadyLoggedOut = false
        parsed.state.accessToken = null
        parsed.state.refreshToken = null
        parsed.state.user = null
        localStorage.setItem('kyapture-auth', JSON.stringify(parsed))
      }
    }
  } catch {
    // Fail silently in non-browser environments
  }

  if (alreadyLoggedOut) {
    return
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth-session-expired'))
  }
}

export default api