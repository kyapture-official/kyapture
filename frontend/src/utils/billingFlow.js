// File Location: frontend/src/utils/billingFlow.js
import { parseApiError } from './apiErrors.js'

// These mirror the server (apps/subscriptions/payments.py), which stays the authority and re-checks every
// one of them. They exist so a typo is caught before an upload, never to decide anything.
export const REFERENCE_MIN = 4
export const REFERENCE_MAX = 64
const REFERENCE_RE = /^[A-Za-z0-9][A-Za-z0-9._/-]{2,62}[A-Za-z0-9]$/

export const PROOF_ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf'
const PROOF_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.pdf']
const PROOF_MIME = ['image/png', 'image/jpeg', 'image/webp', 'application/pdf']
export const DEFAULT_PROOF_MAX_MB = 5

/** '' when the text can be a transaction ID (letters, digits and . _ / -, 4-64 characters, no spaces). */
export function referenceProblem(text) {
  const value = String(text ?? '').trim()
  if (!value) return 'Enter the transaction ID from your payment.'
  if (value.length < REFERENCE_MIN || value.length > REFERENCE_MAX || !REFERENCE_RE.test(value)) {
    return `The transaction ID must be ${REFERENCE_MIN}-${REFERENCE_MAX} characters: letters, numbers, and . _ / - only (no spaces).`
  }
  return ''
}

/** '' when `file` looks like an accepted proof (image or PDF, within the size limit). The server judges the bytes. */
export function proofProblem(file, maxMb = DEFAULT_PROOF_MAX_MB) {
  if (!file) return 'Choose the screenshot or PDF of your payment.'
  const name = String(file.name || '').toLowerCase()
  const typeOk = PROOF_MIME.includes(String(file.type || '').toLowerCase())
  const extensionOk = PROOF_EXTENSIONS.some((extension) => name.endsWith(extension))
  if (!typeOk && !extensionOk) return 'Upload a PNG, JPEG or WEBP image, or a PDF.'
  if (!file.size) return 'That file is empty.'
  if (file.size > maxMb * 1024 * 1024) return `The proof must be ${maxMb} MB or smaller.`
  return ''
}

/** { message, fieldErrors } for a failed submit: the server's own sentence, with its per-field messages. */
export function describeSubmitError(err) {
  const parsed = parseApiError(err, 'Could not submit your payment. Please try again.')
  return { message: parsed.message, fieldErrors: parsed.fieldErrors || {}, code: parsed.code, status: parsed.status }
}

/** The plan the user holds right now: an active subscription whose period has not ended (the server says so too). */
export function livePlanOf(subscription) {
  if (!subscription || subscription.status !== 'active' || subscription.is_expired) return null
  return subscription.plan || null
}

/**
 * What the Billing page should say about the account:
 *   kind     'free' (never paid), 'active' (a live paid plan) or 'lapsed' (a plan whose period ended)
 *   pending  the payments waiting for review
 *   rejected the newest payment when staff rejected it and nothing newer is pending or approved, else null
 * `payments` is the API's list, newest first.
 */
export function billingState({ subscription, payments }) {
  const list = Array.isArray(payments) ? payments : []
  const live = livePlanOf(subscription)
  const hadPlan = Boolean(subscription?.plan) && subscription?.status !== 'no_subscription'
  const newest = list[0] || null
  return {
    kind: live ? 'active' : hadPlan ? 'lapsed' : 'free',
    pending: list.filter((payment) => payment.status === 'pending'),
    rejected: newest && newest.status === 'rejected' ? newest : null,
  }
}

/**
 * What the owner is told about the paid period, from the server's `lifecycle` block (my-subscription; the server
 * computes the state and the calendar days in the billing time zone, the browser only words them):
 *   null                        no paid period to talk about (never subscribed, cancelled, still loading)
 *   { state: 'active', label }  live, far from the end: "Expires in 20 days"
 *   { state: 'expiring', ... }  live and inside the reminder window: "Expires in 2 days" / "Expires today"
 *   { state: 'expired', ... }   the period ended: "Expired" (the account is on the Free plan)
 * `banner` is true for the two states that earn a notice on the dashboard.
 */
export function expiryNotice(lifecycle) {
  const state = lifecycle?.state
  if (state === 'expired') return { state, label: 'Expired', banner: true }
  if (state !== 'active' && state !== 'expiring') return null
  const days = lifecycle.days_left == null ? NaN : Number(lifecycle.days_left)
  if (!Number.isFinite(days) || days < 0) return null
  const label = days === 0 ? 'Expires today' : days === 1 ? 'Expires in 1 day' : `Expires in ${days} days`
  return { state, label, banner: state === 'expiring' }
}

/** One short line for a history row: why it was rejected, or how long the approved plan runs. */
export function paymentDetail(payment, formatDate) {
  if (payment.status === 'rejected') return payment.rejection_reason || 'Not approved.'
  if (payment.status === 'approved') return payment.period_end ? `Plan runs until ${formatDate(payment.period_end)}` : 'Approved'
  return 'Waiting for review'
}
