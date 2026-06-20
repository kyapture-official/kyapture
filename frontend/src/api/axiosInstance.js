import axios from 'axios'

// ─────────────────────────────────────────────────────────────────────────────
// BASE CONFIGURATION & PATH NORMALIZATION
// ─────────────────────────────────────────────────────────────────────────────
const rawBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const cleanBaseURL = rawBaseURL.replace(/\/+$/, '')

const api = axios.create({
  baseURL: cleanBaseURL,
  })

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach((promise) => {
    error ? promise.reject(error) : promise.resolve(token)
  })
  failedQueue = []
}

// ─────────────────────────────────────────────────────────────────────────────
// TOKEN HELPERS
// WHY: Zustand persist stores tokens as a nested object under 'kyapture-auth',
//      not as flat keys. These helpers keep the read/write logic in one place.
// ─────────────────────────────────────────────────────────────────────────────
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

const setAccessToken = (token) => {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    if (persisted) {
      const parsed = JSON.parse(persisted)
      if (parsed?.state) {
        parsed.state.accessToken = token
        localStorage.setItem('kyapture-auth', JSON.stringify(parsed))
      }
    }
  } catch {
    // fail silently
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// REQUEST INTERCEPTOR
// ─────────────────────────────────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    // Zustand persist stores as { state: { accessToken: "..." } }
    const persisted = localStorage.getItem('kyapture-auth')
    const token = persisted ? JSON.parse(persisted)?.state?.accessToken : null
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ─────────────────────────────────────────────────────────────────────────────
// RESPONSE INTERCEPTOR
// ─────────────────────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (!originalRequest) {
      return Promise.reject(error)
    }

    const isAuthRoute =
      originalRequest.url?.includes('/auth/token/refresh/') ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/')

    if (error.response?.status === 401 && !isAuthRoute && !originalRequest._retry) {

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

      const refreshToken = getRefreshToken() // ✅ FIXED: reads from kyapture-auth
      if (!refreshToken) {
        isRefreshing = false
        processQueue(error, null)
        triggerGlobalLogout()
        return Promise.reject(error)
      }

      try {
        const refreshURL = `${cleanBaseURL}/auth/token/refresh/`
        const { data } = await axios.post(
          refreshURL,
          { refresh: refreshToken },
          { timeout: 10_000 }
        )

        const newAccessToken = data.access
        setAccessToken(newAccessToken) // ✅ FIXED: writes back into kyapture-auth

        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`

        isRefreshing = false
        processQueue(null, newAccessToken)

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

// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL LOGOUT DISPATCHER
// ─────────────────────────────────────────────────────────────────────────────
function triggerGlobalLogout() {
  try {
    const persisted = localStorage.getItem('kyapture-auth')
    if (persisted) {
      const parsed = JSON.parse(persisted)
      if (parsed?.state) {
        parsed.state.accessToken = null  // ✅ FIXED: clears inside kyapture-auth
        parsed.state.refreshToken = null
        localStorage.setItem('kyapture-auth', JSON.stringify(parsed))
      }
    }
  } catch {
    // fail silently
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth-session-expired'))
  }
}

export default api