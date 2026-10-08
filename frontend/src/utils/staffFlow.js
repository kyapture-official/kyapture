// File Location: frontend/src/utils/staffFlow.js
import { formatBytes } from './formatters.js'
import { parseApiError } from './apiErrors.js'

// Mirrors the server (apps/users/staff_api.py, audit.py), which stays the authority.
export const REASON_MAX = 300
export const STAFF_PAGE_SIZE = 25

export const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
]

export const STORAGE_OPTIONS = [
  { value: '', label: 'Any storage' },
  { value: 'empty', label: 'Empty' },
  { value: 'near_full', label: '80% or more used' },
  { value: 'full', label: 'Full' },
]

export const SORT_OPTIONS = [
  { value: 'joined', label: 'Newest first' },
  { value: 'storage', label: 'Most storage used' },
  { value: 'email', label: 'Email A-Z' },
]

export const AUDIT_ACTIONS = [
  { value: '', label: 'All actions' },
  { value: 'account.suspend', label: 'Suspended an account' },
  { value: 'account.reactivate', label: 'Reactivated an account' },
  { value: 'security.login_lockout', label: 'Login locked' },
  { value: 'security.gallery_lockout', label: 'Gallery gate locked' },
  { value: 'security.password_reset', label: 'Password reset' },
  { value: 'security.password_change', label: 'Password changed' },
  { value: 'staff.user_list', label: 'Viewed the user list' },
  { value: 'staff.user_lookup', label: 'Looked up a user by email' },
  { value: 'staff.audit_view', label: 'Viewed the audit log' },
  { value: 'staff.inbox_view', label: 'Viewed a staff queue' },
  { value: 'staff.feedback_status', label: 'Changed a feedback status' },
  { value: 'staff.payment_review', label: 'Reviewed a manual payment' },
]

/** The search box takes one complete address; this only saves a round trip, the server re-checks it. */
export const looksLikeEmail = (text) => {
  const value = String(text ?? '').trim()
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 254
}

/** One line of plain text, 1 to REASON_MAX characters (line breaks count as spaces). Returns '' when fine. */
export function reasonProblem(text) {
  const oneLine = String(text ?? '').split(/\s+/).filter(Boolean).join(' ')
  if (!oneLine) return 'Enter a reason.'
  if (oneLine.length > REASON_MAX) return `Keep the reason under ${REASON_MAX} characters.`
  return ''
}

/** Bytes used against the plan limit: { percent (0-100, whole), label, full }. A missing limit reads as 0%. */
export function storageSummary(row) {
  const used = Number(row?.storage_used_bytes) || 0
  const limit = Number(row?.storage_limit_bytes) || 0
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
  return { percent, label: `${formatBytes(used)} of ${formatBytes(limit)}`, full: limit > 0 && used >= limit }
}

/** Staff accounts (the signed-in member included) are changed in the admin, never from this page. */
export const canChangeStatus = (row) => row?.is_staff !== true

const MESSAGES = {
  invalid_email_query: 'Search needs one complete email address.',
  reason_required: 'Enter a reason.',
  reason_too_long: `Keep the reason under ${REASON_MAX} characters.`,
  cannot_change_self: 'You cannot change your own account here.',
  cannot_change_staff: 'Staff accounts are managed in the admin, not here.',
  already_suspended: 'This account is already suspended. Refresh the list.',
  not_suspended: 'This account is not suspended. Refresh the list.',
  not_found: 'That account no longer exists.',
}

/** One human message for a failed staff call. Returns { message, status, code }. */
export function describeStaffError(err) {
  const parsed = parseApiError(err, 'Something went wrong. Please try again.')
  if (parsed.status === 429) {
    const seconds = Number(err?.response?.headers?.['retry-after'])
    const minutes = Math.ceil(seconds / 60)
    const wait = Number.isFinite(seconds) && seconds > 0 ? `in about ${minutes} minute${minutes === 1 ? '' : 's'}` : 'a little later'
    return { message: `Too many requests. Try again ${wait}.`, status: 429, code: 'throttled' }
  }
  if (parsed.status === 403 && !MESSAGES[parsed.code]) {
    return { message: 'Staff access is required.', status: 403, code: parsed.code }
  }
  return { message: MESSAGES[parsed.code] || parsed.message, status: parsed.status, code: parsed.code }
}

/** Plan filter options: Free first, then every plan the plans API returns (keys deduplicated). */
export function planOptions(plans) {
  const seen = new Set(['free'])
  const options = [{ value: '', label: 'All plans' }, { value: 'free', label: 'Free' }]
  for (const plan of plans || []) {
    if (plan?.key && !seen.has(plan.key)) {
      seen.add(plan.key)
      options.push({ value: plan.key, label: plan.name || plan.key })
    }
  }
  return options
}

export const statusLabel = (status) => (status === 'suspended' ? 'Suspended' : 'Active')
