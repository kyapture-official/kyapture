import { create } from 'zustand'
import { authApi } from '../api/authApi'

export const useAuthStore = create((set, get) => ({
  user: null,
  isAuthenticated: false,
  loading: true,

  init: async () => {
    const token = localStorage.getItem('access_token')
    if (!token) return set({ loading: false })
    try {
      const { data } = await authApi.me()
      set({ user: data, isAuthenticated: true, loading: false })
    } catch {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      set({ loading: false })
    }
  },

  login: async (email, password) => {
    const { data } = await authApi.login({ email, password })
    localStorage.setItem('access_token',  data.access)
    localStorage.setItem('refresh_token', data.refresh)
    set({ user: data.user, isAuthenticated: true })
    return data
  },

  register: async (payload) => {
    const { data } = await authApi.register(payload)
    localStorage.setItem('access_token',  data.access)
    localStorage.setItem('refresh_token', data.refresh)
    set({ user: data.user, isAuthenticated: true })
    return data
  },

  logout: async () => {
    try {
      await authApi.logout({ refresh: localStorage.getItem('refresh_token') })
    } catch {}
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null, isAuthenticated: false })
  },

  updateUser: (data) => set({ user: { ...get().user, ...data } }),
}))
