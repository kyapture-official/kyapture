// File Location: frontend/src/api/feedbackApi.js
import api from './axiosInstance'

/** Endpoints are documented in docs/KYAPTURE_FEEDBACK.md; the server enforces who may call which. */
export const feedbackApi = {
  /** POST /feedback/ { category, subject?, message, route, app_version } -> the created row (201) */
  submit: async (payload) => {
    const { data } = await api.post('/feedback/', payload)
    return data
  },

  /** GET /feedback/inbox/?status=&category=&page= (staff only) -> { count, next, previous, results } newest first */
  inbox: async ({ status = '', category = '', page = 1 } = {}, signal = undefined) => {
    const params = { page }
    if (status) params.status = status
    if (category) params.category = category
    const { data } = await api.get('/feedback/inbox/', { params, signal })
    return data
  },

  /** PATCH /feedback/inbox/{id}/ { status } (staff only; status is the only writable field) -> the updated row */
  setStatus: async (id, status) => {
    const { data } = await api.patch(`/feedback/inbox/${id}/`, { status })
    return data
  },
}
