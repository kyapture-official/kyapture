import { create } from 'zustand'
import { authApi } from '../api/authApi'

// ─────────────────────────────────────────────────────────────────────────────
// MODULE-LEVEL INITIALIZATION MUTEX
// Holds a single thread-safety lock across the application's runtime.
// ─────────────────────────────────────────────────────────────────────────────
let _initCalled = false

export const useAuthStore = create((set, get) => ({
  // ── INITIAL STATE ──────────────────────────────────────────────────────────
  user: null,
  isAuthenticated: false,
  loading: true,

  // ── ACTIONS ────────────────────────────────────────────────────────────────

  /**
   * WHAT: Session Re-hydration Action
   * WHY:  Validates current JWT values against the backend /me profile on app boot.
   *       Runs at root App.jsx level; protected by an initialization mutex [4].
   */
  init: async () => {
    if (_initCalled) return
    _initCalled = true

    const token = localStorage.getItem('access_token')
    if (!token) {
      return set({ loading: false, isAuthenticated: false })
    }

    try {
      const { data } = await authApi.me()
      set({ user: data, isAuthenticated: true, loading: false })
    } catch {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      set({ user: null, isAuthenticated: false, loading: false })
    }
  },

  /**
   * WHAT: Login Action
   * WHY:  Submits email/password, caches JWT tokens in storage, and loads profile.
   */
  login: async (email, password) => {
    const { data } = await authApi.login({ email, password })
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    set({ user: data.user, isAuthenticated: true, loading: false })
    return data
  },

  /**
   * WHAT: Registration Action
   * WHY:  Registers photographer and logs them in immediately.
   */
  register: async (payload) => {
    const { data } = await authApi.register(payload)
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    set({ user: data.user, isAuthenticated: true, loading: false })
    return data
  },

  /**
   * WHAT: Logout Action
   * WHY:  Blacklists tokens on backend, purges local cache, and resets initialization locks.
   */
  logout: async () => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      try {
        await authApi.logout({ refresh: refreshToken })
      } catch (err) {
        console.warn('Refresh token blacklisting failed — proceeding with local logout:', err)
      }
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    
    // Reset mutex lock to allow subsequent logins to re-initialize
    _initCalled = false
    
    set({ user: null, isAuthenticated: false, loading: false })
  },

  /**
   * WHAT: Password Recovery Request Action
   * WHY:  Dispatches the recovery email request payload to the API reset endpoint.
   */
  forgotPassword: async (email) => {
    await authApi.forgotPassword({ email })
  },

  /**
   * WHAT: Partial User State Updater
   * WHY:  Optimistically updates cached profile details (avatars, names) on the client.
   *       Defensively guarded against unauthenticated execution paths [3].
   */
  updateUser: (updatedFields) => {
    const currentUser = get().user
    if (!currentUser) return
    set({ user: { ...currentUser, ...updatedFields } })
  },
}))

// ─────────────────────────────────────────────────────────────────────────────
// EXTERNAL EVENT SYNCHRONIZER
// Sets up a HMR-safe event listener using Zustand's public stable API [16].
// ─────────────────────────────────────────────────────────────────────────────
if (typeof window !== 'undefined') {
  const HANDLER_KEY = '__authSessionExpiredHandler'

  // If a handler is already bound from a prior HMR file execution, tear it down [16]
  if (window[HANDLER_KEY]) {
    window.removeEventListener('auth-session-expired', window[HANDLER_KEY])
  }

  // Bind new single instance to the global window context [16]
  window[HANDLER_KEY] = () =>
    useAuthStore.setState({ user: null, isAuthenticated: false, loading: false })

  window.addEventListener('auth-session-expired', window[HANDLER_KEY])
}