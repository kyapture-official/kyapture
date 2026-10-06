// File Location: frontend/src/utils/feedbackFlow.js
import { APP_VERSION } from './appVersion.js'
import { parseApiError } from './apiErrors.js'

// Limits mirror Feedback.SUBJECT_MAX / MESSAGE_MAX on the server, which stays the authority.
export const SUBJECT_MAX = 120
export const MESSAGE_MAX = 4000

export const FEEDBACK_CATEGORIES = [
  { value: 'bug', label: 'Bug' },
  { value: 'feature_request', label: 'Feature request' },
  { value: 'design', label: 'Design' },
  { value: 'performance', label: 'Performance' },
  { value: 'download', label: 'Download' },
  { value: 'upload', label: 'Upload' },
  { value: 'security_privacy', label: 'Security / privacy' },
  { value: 'other', label: 'Other' },
]

export const FEEDBACK_STATUSES = [
  { value: 'new', label: 'New' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'dismissed', label: 'Dismissed' },
]

export const labelOf = (options, value) => options.find((o) => o.value === value)?.label ?? String(value ?? '')

/** The widget is for the signed-in photographer's dashboard and gallery workspace only. */
export const widgetVisibleOn = (pathname) =>
  typeof pathname === 'string' && (pathname === '/dashboard' || pathname.startsWith('/dashboard/'))

/** The gallery workspace (/dashboard/galleries/:id/...) has fixed bottom bars on phones; the list page has none. */
export const isWorkspacePath = (pathname) => typeof pathname === 'string' && /^\/dashboard\/galleries\/[^/]+/.test(pathname)

/** Path only: never a query string, fragment or full URL (they can carry tokens, PINs or signed links). */
export const pathOnly = (value) => {
  if (typeof value !== 'string') return ''
  const path = value.split('#', 1)[0].split('?', 1)[0]
  return path.startsWith('/') && !path.startsWith('//') ? path : ''
}

/** Field problems found before any request; the server re-checks all of it. */
export function validateFeedback({ category, subject, message }) {
  const errors = {}
  if (!FEEDBACK_CATEGORIES.some((c) => c.value === category)) errors.category = 'Choose a category.'
  if (!String(message ?? '').trim()) errors.message = 'Tell us what happened.'
  else if (String(message).trim().length > MESSAGE_MAX) errors.message = `Keep it under ${MESSAGE_MAX} characters.`
  if (String(subject ?? '').trim().length > SUBJECT_MAX) errors.subject = `Keep it under ${SUBJECT_MAX} characters.`
  return errors
}

/**
 * The submit body. Besides the three form fields it carries only the current
 * path and the build's app version. An empty subject is left out (it is optional).
 */
export function buildFeedbackPayload({ category, subject, message }, pathname, appVersion = APP_VERSION) {
  const payload = {
    category,
    message: String(message).trim(),
    route: pathOnly(pathname),
    app_version: appVersion,
  }
  const cleanSubject = String(subject ?? '').trim()
  if (cleanSubject) payload.subject = cleanSubject
  return payload
}

const retryMinutes = (err) => {
  const seconds = Number(err?.response?.headers?.['retry-after'])
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds / 60) : null
}

/**
 * One human message for a failed feedback call. `kind` is 'submit' (the widget),
 * 'inbox' (list) or 'status' (change). Returns { message, fieldErrors, status }.
 */
export function describeFeedbackError(err, kind) {
  const parsed = parseApiError(err, kind === 'submit' ? 'Could not send your feedback. Please try again.' : 'Something went wrong. Please try again.')
  const status = parsed.status
  if (status === 429) {
    const minutes = retryMinutes(err)
    const wait = minutes ? `in about ${minutes} minute${minutes === 1 ? '' : 's'}` : 'a little later'
    return {
      message: kind === 'submit'
        ? `You have sent several messages recently. Your text is kept; try again ${wait}.`
        : `Too many requests. Please try again ${wait}.`,
      fieldErrors: {},
      status,
    }
  }
  if (status === 403) {
    return {
      message: kind === 'submit'
        ? 'Your account is not allowed to send feedback right now.'
        : 'Staff access is required. This account cannot view or change feedback.',
      fieldErrors: {},
      status,
    }
  }
  // parseApiError treats a key named `message` as a non-field key, but here it is a real form field.
  const fieldErrors = { ...parsed.fieldErrors }
  const raw = err?.response?.data
  const container = raw?.details && typeof raw.details === 'object' ? raw.details : raw
  const messageProblem = [container?.message].flat()[0]
  if (status === 400 && typeof messageProblem === 'string') fieldErrors.message = messageProblem
  return { message: parsed.message, fieldErrors, status }
}
