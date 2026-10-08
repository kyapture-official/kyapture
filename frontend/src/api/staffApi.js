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

  // ── 7.5-B: manual payment review. The server decides everything (staff only, the row lock, the
  //    plan, the audit row); these calls only present what it returns. docs/KYAPTURE_PAYMENTS.md.

  /** GET /staff/payments/?status=pending|approved|rejected|all&page= -> { count, next, previous, results } */
  payments: async ({ status = 'pending', page = 1 } = {}, signal = undefined) => {
    const { data } = await api.get('/staff/payments/', { params: { status, page }, signal })
    return data
  },

  /** POST /staff/payments/{id}/approve/ -> { changed, code, message, payment } (a repeat answers changed: false) */
  approvePayment: async (id) => {
    const { data } = await api.post(`/staff/payments/${id}/approve/`, {})
    return data
  },

  /** POST /staff/payments/{id}/reject/ { reason } -> { changed, code, message, payment } */
  rejectPayment: async (id, reason) => {
    const { data } = await api.post(`/staff/payments/${id}/reject/`, { reason })
    return data
  },

  /** POST /staff/payments/{id}/proof-link/ -> { url, expires_in, content_type }: a signed link, valid a few minutes. */
  paymentProofLink: async (id) => {
    const { data } = await api.post(`/staff/payments/${id}/proof-link/`, {})
    return data
  },
}
