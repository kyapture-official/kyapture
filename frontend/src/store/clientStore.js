// frontend/src/store/clientStore.js
// FIXED: store now actually exposes what ClientGalleryPage.jsx and
// DownloadPage.jsx call — `sessions` + `setSession(key, token)` — instead
// of the half-finished `unlockTokens`/`setUnlockToken` API that nothing
// in the app ever correctly wired up.

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { useVisitorStore } from './visitorStore'

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

      // Phase 3 — favorites identity for OPEN (non-password-protected)
      // galleries, which have no session/token concept at all. A random
      // per-gallery id, generated once and persisted the same way (and in
      // the same sessionStorage-backed store) as the unlock tokens above —
      // "persists across refresh" is exactly what sessionStorage gives.
      // Map: { 'username:gallery-slug' → 'client-uid' }
      clientUids: {},

      // Remembered DOWNLOAD authorization, one per gallery — earned by the
      // explicit Download step (email + PIN when the gallery needs them),
      // never by merely opening or browsing the gallery. Holds the
      // short-lived signed download_token the server issued, so the client
      // isn't asked for email/PIN again for every photo. Same
      // sessionStorage lifetime as the unlock tokens above (gone when the
      // tab closes) plus the server's own expiry. The PIN itself is never
      // stored — only the token.
      // Map: { 'username:gallery-slug' → { token, email, expiresAt (ms) } }
      downloadAccess: {},

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

      /**
       * WHAT: Remember a freshly issued download access token for a gallery.
       */
      setDownloadAccess: (sessionKey, access) => {
        if (!sessionKey) return
        set((state) => {
          const next = { ...state.downloadAccess }
          if (!access) {
            delete next[sessionKey]
          } else {
            next[sessionKey] = access
          }
          return { downloadAccess: next }
        })
      },

      /**
       * WHAT: The remembered download access for a gallery, or null once it
       *       has expired (or was never earned). Synchronous, usable
       *       outside render.
       */
      getDownloadAccess: (sessionKey) => {
        if (!sessionKey) return null
        const access = get().downloadAccess[sessionKey]
        if (!access || !access.token || !(access.expiresAt > Date.now())) return null
        return access
      },

      /**
       * WHAT: Returns this gallery's client_uid, generating and persisting
       *       one on first call if none exists yet.
       */
      getOrCreateClientUid: (sessionKey) => {
        if (!sessionKey) return null
        // The identity now lives in visitorStore (localStorage) so a visitor's
        // favorite lists survive closing the tab; an id this tab already had in
        // sessionStorage is adopted rather than orphaning its favorites.
        const uid = useVisitorStore.getState().getOrCreateClientUid(sessionKey, get().clientUids[sessionKey])
        if (get().clientUids[sessionKey] !== uid) {
          set((state) => ({ clientUids: { ...state.clientUids, [sessionKey]: uid } }))
        }
        return uid
      },
    }),
    {
      name:    'client-session-storage',
      storage: createJSONStorage(getBrowserSessionStorage),
      partialize: (state) => ({
        sessions: state.sessions,
        clientUids: state.clientUids,
        downloadAccess: state.downloadAccess,
      }),

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