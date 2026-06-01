import api from './axiosInstance'

export const galleriesApi = {
  list:         ()         => api.get('/galleries/'),
  create:       (data)     => api.post('/galleries/', data),
  get:          (id)       => api.get(`/galleries/${id}/`),
  update:       (id, data) => api.patch(`/galleries/${id}/`, data),
  delete:       (id)       => api.delete(`/galleries/${id}/`),
  publish:      (id)       => api.post(`/galleries/${id}/publish/`),
  unpublish:    (id)       => api.post(`/galleries/${id}/unpublish/`),
}
