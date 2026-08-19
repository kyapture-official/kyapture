// frontend/src/api/clientsApi.js

import api from './axiosInstance'
import axios from 'axios'

const publicApi = axios.create({ baseURL: '/api/v1' })

export const clientsApi = {
  // Public: get gallery by photographer username + slug.
  // token: the gallery unlock token, sent as ?token= so the backend can
  //   validate a returning client's session for a password-protected gallery.
  // config: optional Axios config (e.g. { signal }) forwarded through for
  //   request cancellation — needed so an AbortController from the calling
  //   component actually reaches the underlying HTTP request instead of
  //   being silently dropped.
  getGallery: (username, slug, token, config = {}) =>
    publicApi.get(`/public/${username}/${slug}/`, {
      params: token ? { token } : {},
      ...config,
    }),

  // Unlock password-protected gallery.
  unlock: (username, slug, password, config = {}) =>
    publicApi.post(`/public/${username}/${slug}/unlock/`, { password }, config),

  // List photographer's public galleries (client home)
  listGalleries: (username, config = {}) =>
    publicApi.get(`/public/${username}/`, config),

  // Download token
  requestDownload: (token, galleryId, config = {}) =>
    publicApi.post(`/public/download/${galleryId}/`, {}, {
      headers: { 'X-Client-Token': token },
      ...config,
    }),
}