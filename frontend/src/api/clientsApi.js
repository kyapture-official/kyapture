import api from './axiosInstance'
import axios from 'axios'

const publicApi = axios.create({ baseURL: '/api/v1' })

export const clientsApi = {
  // Public: get gallery by photographer username + slug
  getGallery: (username, slug) =>
    publicApi.get(`/public/${username}/${slug}/`),

  // Unlock password-protected gallery
  unlock: (username, slug, password) =>
    publicApi.post(`/public/${username}/${slug}/unlock/`, { password }),

  // List photographer's public galleries (client home)
  listGalleries: (username) =>
    publicApi.get(`/public/${username}/`),

  // Download token
  requestDownload: (token, galleryId) =>
    publicApi.post(`/public/download/${galleryId}/`, {}, {
      headers: { 'X-Client-Token': token },
    }),
}
