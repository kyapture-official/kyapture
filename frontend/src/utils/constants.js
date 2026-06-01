export const BASE_URL = import.meta.env.VITE_API_URL || ''
export const MEDIA_URL = import.meta.env.VITE_MEDIA_URL || ''

export const PAYMENT_METHODS = [
  { value: 'esewa',  label: 'eSewa' },
  { value: 'khalti', label: 'Khalti' },
  { value: 'bank',   label: 'Bank Transfer' },
  { value: 'manual', label: 'Manual' },
]

export const SUBSCRIPTION_STATUS_COLORS = {
  active:    'bg-emerald-100 text-emerald-700',
  expired:   'bg-red-100 text-red-700',
  cancelled: 'bg-stone-100 text-stone-600',
  pending:   'bg-amber-100 text-amber-700',
}
