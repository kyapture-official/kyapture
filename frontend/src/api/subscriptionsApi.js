import api from './axiosInstance'

export const subscriptionsApi = {
  plans:          ()     => api.get('/subscriptions/plans/'),
  mySubscription: ()     => api.get('/subscriptions/me/'),
  submitPayment:  (data) =>
    api.post('/subscriptions/payments/', data, {
      headers: data instanceof FormData ? { 'Content-Type': 'multipart/form-data' } : {},
    }),
  paymentHistory: ()     => api.get('/subscriptions/payments/'),
}
