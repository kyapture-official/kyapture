// File Location: frontend/src/store/clientStore.js
// VERSION: Production Hardened — Week 10
// Resolves TDZ reference crashes and prevents SecurityError DOMExceptions in privacy browsers.

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// ── SSR & PRIVACY SANDBOX MOCK STORAGE ──────────────────────────────────────
const noopStorage = {
  getItem:    () => null,
  setItem:    () => {},
  removeItem: () => {},
}

/**
 * WHAT: Defensive Browser Storage Capabilities Tester
 * WHY:  Accessing window.sessionStorage directly in privacy-hardened environments, 
 *       strict sandboxes, or incognito modes throws a DOMException SecurityError.
 *       Testing read/write capabilities ensures we fallback gracefully.
 */
const getBrowserSessionStorage = () => {
  if (typeof window === 'undefined') return noopStorage
  
  try {
    const storage = window.sessionStorage
    const testKey = '__kyapture_storage_test__'
    
    // Perform capability flight test
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
    (set) => ({
      // Map: { 'username:gallery-slug' → 'signed-access-token' }
      // Scoped by username:slug to prevent slug collisions across photographers.
      sessions:     {},
      hasHydrated:  false,

      setSession: (sessionKey, token) => {
        if (typeof sessionKey !== 'string' || !sessionKey.trim()) return
        set((state) => {
          const next = { ...state.sessions }
          if (token === null) {
            // token === null → delete the entry entirely rather than keeping null values
            delete next[sessionKey]
          } else {
            next[sessionKey] = token
          }
          return { sessions: next }
        })
      },
    }),
    {
      name:    'client-session-storage',
      storage: createJSONStorage(getBrowserSessionStorage),

      // Exclude 'hasHydrated' from storage serialization
      partialize: (state) => ({ sessions: state.sessions }),

      // ── TDZ RESOLUTION ─────────────────────────────────────────────────────
      // If storage is warm, rehydration runs synchronously during store creation
      // before assignment to useClientStore completes. We mutate the state
      // parameter directly to inject hasHydrated: true during the initial commit
      // phase, bypassing reference TDZs.
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.error('[clientStore] Session rehydration failed:', error)
          return
        }
        if (state) {
          state.hasHydrated = true
        }
      },
    }
  )
)