// File Location: frontend/src/api/staffApi.js
import api from './axiosInstance'

/**
 * The staff area (7.5-A). The server enforces is_staff on every route (403 to anyone else);
 * these calls only present what it returns. Documented in docs/KYAPTURE_STAFF.md.
 */
export const staffApi = {
  /** GET /staff/users/?q=<exact email>&plan=&status=&storage=&sort=&page= -> { count, next, previous, results } */
  users: async (filters = {}, signal = undefined) => {
    const params = {}
    for (const key of ['q', 'plan', 'status', 'storage', 'sort']) {
      if (filters[key]) params[key] = filters[key]
    }
    params.page = filters.page || 1
    const { data } = await api.get('/staff/users/', { params, signal })
    return data
  },

  /** POST /staff/users/{id}/suspend/ { reason } -> the updated user row */
  suspend: async (id, reason) => {
    const { data } = await api.post(`/staff/users/${id}/suspend/`, { reason })
    return data
  },

  /** POST /staff/users/{id}/reactivate/ { reason } -> the updated user row */
  reactivate: async (id, reason) => {
    const { data } = await api.post(`/staff/users/${id}/reactivate/`, { reason })
    return data
  },

  /** GET /staff/audit/?action=&page= (read only) -> { count, next, previous, results } newest first */
  audit: async ({ action = '', page = 1 } = {}, signal = undefined) => {
    const params = { page }
    if (action) params.action = action
    const { data } = await api.get('/staff/audit/', { params, signal })
    return data
  },
}
