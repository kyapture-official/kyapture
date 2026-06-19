import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// ── ISOMORPHIC SESSION STORAGE GETTER ────────────────────────────────────
// sessionStorage doesn't exist inside Node SSR runtimes. Fall back to a
// silent no-op so module evaluation never throws on the server; real
// sessionStorage is used as soon as we're in a browser.
const noopStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
const getBrowserSessionStorage = () =>
  typeof window !== 'undefined' ? window.sessionStorage : noopStorage

/**
 * Normalizes input slugs defensively: enforces string type, trims
 * whitespace, and rejects empty strings so two "different" slugs can
 * never collide on the same storage key.
 */
const normalizeSlug = (slug) => {
  if (typeof slug !== 'string') return null
  const trimmed = slug.trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * WHAT: Transient Client Session Store
 * WHY:  Caches gallery-unlock tokens in the browser's sessionStorage.
 *       Keying by gallery slug means a single tab can hold tokens for
 *       several unlocked galleries at once without one overwriting
 *       another. (sessionStorage is already isolated per tab by the
 *       browser itself — this map isn't what protects against cross-tab
 *       collisions, it's what protects against cross-gallery collisions
 *       within one tab.)
 *       Using sessionStorage over localStorage shortens how long a leaked
 *       token stays valid; it does not protect the token from an XSS
 *       payload running on the same page, which can read it just as
 *       easily as it could read localStorage.
 */
export const useClientStore = create(
  persist(
    (set, get) => ({
      // State map: { 'gallery-slug': 'signed-access-token' }
      unlockTokens: {},

      // True once rehydration from sessionStorage has finished (success
      // or error). Lets the UI avoid flashing a "locked" state before the
      // cached token has had a chance to load. Always false on the
      // server, since hydration is skipped there — see skipHydration.
      hasHydrated: false,

      /**
       * WHAT: Cache Unlock Token Action
       * WHY:  Saves a newly issued access token mapped to the gallery's slug.
       */
      setUnlockToken: (slug, token) => {
        const key = normalizeSlug(slug)
        if (!key || typeof token !== 'string') return
        const value = token.trim()
        if (!value) return
        set((state) => ({
          unlockTokens: { ...state.unlockTokens, [key]: value },
        }))
      },

      /**
       * WHAT: Retrieve Token Selector
       * WHY:  Exposes a safe, synchronous getter to extract a cached token.
       */
      getUnlockToken: (slug) => {
        const key = normalizeSlug(slug)
        if (!key) return null
        return get().unlockTokens[key] ?? null
      },

      /**
       * WHAT: Revoke Token Action
       * WHY:  Explicitly clears a cached token when a client session expires.
       *       Returns the original state object if the key is already
       *       missing, so zustand skips the update and no re-render fires.
       */
      revokeToken: (slug) => {
        const key = normalizeSlug(slug)
        if (!key) return
        set((state) => {
          if (!(key in state.unlockTokens)) return state
          const next = { ...state.unlockTokens }
          delete next[key]
          return { unlockTokens: next }
        })
      },

      /**
       * WHAT: Clear All Tokens Action
       * WHY:  Purges the entire session cache.
       */
      clearAllTokens: () => {
        set({ unlockTokens: {} })
      },
    }),
    {
      name: 'client-session-storage',
      storage: createJSONStorage(getBrowserSessionStorage),
      // Skip auto-rehydration on the server — there's no sessionStorage to
      // read from there. The client bundle hydrates normally on mount.
      skipHydration: typeof window === 'undefined',
      // Whitelist what gets WRITTEN to sessionStorage. The action
      // functions were never going to serialize anyway (JSON.stringify
      // drops them) and stay fully intact on the live in-memory store
      // either way — this option only controls the persisted snapshot.
      // As a side benefit, any future non-persisted field (like
      // hasHydrated) is excluded by default instead of needing to
      // remember to add it to an exclusion list.
      partialize: (state) => ({ unlockTokens: state.unlockTokens }),
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.error('Failed to rehydrate client session store:', error)
        }
        useClientStore.setState({ hasHydrated: true })
      },
    }
  )
)