// File Location: frontend/src/api/notificationsApi.js
import api from './axiosInstance'

/**
 * The photographer's dashboard bell. Every call is scoped to the signed-in
 * account by the server; read state lives server-side, so it survives a refresh.
 */
export const notificationsApi = {
  /** GET /notifications/?page=N -> { results, unread_count, count, next, previous } (newest activity first) */
  list: async (page = 1, signal = undefined) => {
    const { data } = await api.get('/notifications/', { params: { page }, signal })
    return data
  },

  /** GET /notifications/unread-count/ -> { unread_count } — one indexed COUNT, cheap to poll. */
  unreadCount: async (signal = undefined) => {
    const { data } = await api.get('/notifications/unread-count/', { signal })
    return data
  },

  /** POST /notifications/{id}/read/ -> { id, is_read, unread_count } (idempotent) */
  markRead: async (id) => {
    const { data } = await api.post(`/notifications/${id}/read/`, {})
    return data
  },

  /** POST /notifications/read-all/ -> { marked, unread_count } */
  markAllRead: async () => {
    const { data } = await api.post('/notifications/read-all/', {})
    return data
  },
}
