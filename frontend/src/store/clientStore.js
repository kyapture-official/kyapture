import { create } from 'zustand'

export const useClientStore = create((set) => ({
  sessions: {},  // galleryId -> accessToken
  setSession: (galleryId, token) =>
    set((s) => ({ sessions: { ...s.sessions, [galleryId]: token } })),
  getSession: (galleryId) => (state) => state.sessions[galleryId],
}))
