import api from './axiosInstance'

export const photosApi = {
  list:   (galleryId)       => api.get(`/photos/?gallery=${galleryId}`),
  upload: (galleryId, formData) =>
    api.post(`/photos/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { gallery: galleryId },
    }),
  delete: (id)              => api.delete(`/photos/${id}/`),
  reorder:(data)            => api.post('/photos/reorder/', data),
}
