import api from './axiosInstance'

export const authApi = {
  register: (data) => api.post('/auth/register/', data),
  login:    (data) => api.post('/auth/login/', data),
  logout:   (data) => api.post('/auth/logout/', data),
  me:       ()     => api.get('/auth/me/'),
  updateMe: (data) => api.put('/auth/me/', data, {
    headers: data instanceof FormData ? { 'Content-Type': 'multipart/form-data' } : {},
  }),
  changePassword: (data) => api.put('/auth/change-password/', data),
}
