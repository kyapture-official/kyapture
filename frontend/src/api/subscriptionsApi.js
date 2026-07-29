import api from './axiosInstance'

/**
 * WHAT: Network Service Client for Subscription, Plans, and Payment Endpoints.
 * WHY:  Abstracts plan listing, history tracking, and manual payment receipt uploads.
 *       Maintains complete RESTful URL alignments.
 */
export const subscriptionsApi = {
  // GET: Fetches pricing tiers ordered by price
  plans: () => 
    api.get('/subscriptions/plans/'),

  // GET: Fetches authenticated user subscription state & quotas (falls back safely via redirect)
  mySubscription: () => 
    api.get('/subscriptions/me/'),

  // POST: Submits receipt screenshots for administrative verification
  submitPayment: (data) =>
    // Fixed: Completely removed the manual 'Content-Type' header override.
    // Leaving headers empty lets Axios and the browser automatically assign the 
    // correct 'multipart/form-data; boundary=----...' parameters so S3 uploads don't crash.
    api.post('/subscriptions/payments/', data),

  // GET: Fetches history logs (scoped per-user on backend)
  paymentHistory: () => 
    api.get('/subscriptions/payments/'),
}