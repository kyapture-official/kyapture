// frontend/src/store/visitorStore.js
//
// What a guest visitor of a gallery has told us about THEMSELVES, remembered in
// this browser (localStorage) so they are asked once, not on every visit:
//
//   profiles  { 'username:slug' -> { email, name } }   the email (+ optional name)
//             given at the first heart; reused for favorites and downloads
//   uids      { 'username:slug' -> 'client-uid' }      the anonymous identity that
//             owns this browser's favorite lists in an OPEN gallery. Persisting it
//             is what lets a visitor come back later and still see their lists.
//
// Unlock tokens and download tokens deliberately stay in clientStore's
// sessionStorage (they end with the tab); only these two harmless, visitor-owned
// facts live longer. Nothing here is a credential for the photographer side.

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

const noopStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }

const getLocalStorage = () => {
  if (typeof window === 'undefined') return noopStorage
  try {
    const storage = window.localStorage
    storage.setItem('__kyapture_visitor_test__', '1')
    storage.removeItem('__kyapture_visitor_test__')
    return storage
  } catch {
    return noopStorage
  }
}

const newUid = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`

export const useVisitorStore = create(
  persist(
    (set, get) => ({
      profiles: {},
      uids: {},

      getProfile: (key) => (key ? get().profiles[key] || null : null),

      setProfile: (key, profile) => {
        if (!key) return
        set((state) => ({
          profiles: { ...state.profiles, [key]: { email: profile?.email || '', name: profile?.name || '' } },
        }))
      },

      /** This browser's anonymous favorites identity for a gallery; `seed` adopts an older sessionStorage one. */
      getOrCreateClientUid: (key, seed = null) => {
        if (!key) return null
        const existing = get().uids[key]
        if (existing) return existing
        const uid = seed || newUid()
        set((state) => ({ uids: { ...state.uids, [key]: uid } }))
        return uid
      },
    }),
    {
      name: 'kyapture-visitor',
      storage: createJSONStorage(getLocalStorage),
      partialize: (state) => ({ profiles: state.profiles, uids: state.uids }),
    },
  ),
)
