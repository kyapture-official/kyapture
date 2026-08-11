// frontend/src/store/clientStore.js
// FIXED: store now actually exposes what ClientGalleryPage.jsx and
// DownloadPage.jsx call — `sessions` + `setSession(key, token)` — instead
// of the half-finished `unlockTokens`/`setUnlockToken` API that nothing
// in the app ever correctly wired up.

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// ── SSR & PRIVACY SANDBOX MOCK STORAGE ──────────────────────────────────────
const noopStorage = {
  getItem:    () => null,
  setItem:    () => {},
  removeItem: () => {},
}

const getBrowserSessionStorage = () => {
  if (typeof window === 'undefined') return noopStorage

  try {
    const storage = window.sessionStorage
    const testKey = '__kyapture_storage_test__'
    storage.setItem(testKey, '1')
    storage.removeItem(testKey)
    return storage
  } catch (err) {
    console.warn(
      '[clientStore] Browser sessionStorage access is restricted by privacy policies. Falling back to transient in-memory storage.',
      err.message
    )
    return noopStorage
  }
}

// ── STORE DEFINITION ─────────────────────────────────────────────────────────
export const useClientStore = create(
  persist(
    (set, get) => ({
      // Map: { 'username:gallery-slug' → 'signed-access-token' }
      sessions: {},

      hasHydrated: false,
      setHasHydrated: (value) => set({ hasHydrated: value }),

      /**
       * WHAT: Save or clear the unlock token for one gallery session.
       * WHY:  token === null (or undefined) explicitly removes the entry
       *       instead of storing a useless null value.
       */
      setSession: (sessionKey, token) => {
        if (!sessionKey) return
        set((state) => {
          const next = { ...state.sessions }
          if (token === null || token === undefined) {
            delete next[sessionKey]
          } else {
            next[sessionKey] = token
          }
          return { sessions: next }
        })
      },

      /**
       * WHAT: Synchronous getter, useful outside React render.
       */
      getSession: (sessionKey) => {
        if (!sessionKey) return null
        return get().sessions[sessionKey] ?? null
      },
    }),
    {
      name:    'client-session-storage',
      storage: createJSONStorage(getBrowserSessionStorage),
      partialize: (state) => ({ sessions: state.sessions }),

      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.error('[clientStore] Session rehydration failed:', error)
          return
        }
        state?.setHasHydrated(true)
      },
    }
  )
)