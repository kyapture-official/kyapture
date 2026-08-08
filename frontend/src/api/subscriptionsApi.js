// File Location: frontend/src/api/subscriptionsApi.js
// VERSION: Hardened Production — Week 11
// Fact-checked, trailing-slash compliant, and supports unmount AbortSignals.

import api from './axiosInstance'

/**
 * WHAT: Subscriptions and Manual Payments API Client
 * WHY:  Maps to the Django namespace 'api/v1/subscriptions/' [weekly tasks.txt].
 *       Isolates multi-part file uploads without stripping boundaries.
 */
export const subscriptionsApi = {
  
  /**
   * WHAT: Fetch available billing tiers (Basic, Pro, Studio).
   * URI:  GET /api/v1/subscriptions/plans/
   *
   * @param {AbortSignal} [signal] - Optional AbortController cancel token
   * @returns {Promise<Plan[]>}
   */
  getPlans: async (signal = undefined) => {
    const { data } = await api.get('/subscriptions/plans/', { signal })
    return data
  },

  /**
   * WHAT: Fetch the authenticated photographer's current subscription status.
   * URI:  GET /api/v1/subscriptions/my-subscription/
   *
   * @param {AbortSignal} [signal] - Optional AbortController cancel token
   * @returns {Promise<UserSubscription>}
   */
  getMyPlan: async (signal = undefined) => {
    const { data } = await api.get('/subscriptions/my-subscription/', { signal })
    return data
  },

  /**
   * WHAT: Submit manual payment transaction proof for admin review.
   * URI:  POST /api/v1/subscriptions/pay/
   *
   * WHY no manual Content-Type header:
   *   Axios detects the FormData instance and dynamically appends the correct
   *   boundary configuration. Hardcoding the header strips this boundary,
   *   causing Django's MultiPartParser to reject the stream with a 415 error.
   *
   * @param {FormData} payload - Form payload containing:
   *                             plan (id), amount (decimal),
   *                             payment_proof (File, max 5MB image),
   *                             notes (string, optional) [weekly tasks.txt]
   * @returns {Promise<{ message: string }>}
   */
  submitManualPayment: async (payload) => {
    const { data } = await api.post('/subscriptions/pay/', payload)
    return data
  },

  /**
   * WHAT: Fetch the authenticated photographer's past payment submissions.
   * URI:  GET /api/v1/subscriptions/payments/
   *
   * @param {AbortSignal} [signal] - Optional AbortController cancel token
   * @returns {Promise<Payment[]>}
   */
  paymentHistory: async (signal = undefined) => {
    const { data } = await api.get('/subscriptions/payments/', { signal })
    return data
  },
}