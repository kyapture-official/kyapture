// File Location: frontend/src/utils/apiErrors.js

const NON_FIELD_KEYS = new Set(['error', 'code', 'detail', 'message', 'details', 'non_field_errors'])

const firstMessage = (value) => {
  if (Array.isArray(value)) return firstMessage(value[0])
  if (value && typeof value === 'object') return firstMessage(Object.values(value)[0])
  return typeof value === 'string' ? value : null
}

/**
 * WHAT: Normalizes a failed API call into { message, fieldErrors, code, status }.
 * WHY:  The backend answers validation failures in two shapes — a raw DRF map
 *       ({ field: ['msg'] }) from views that return serializer.errors, and the
 *       project's wrapped shape ({ error, details: { field: ['msg'] } }) from
 *       the global exception handler. Settings forms need both as per-field
 *       messages, plus a general message for non-field failures, and must
 *       never show a raw exception or invent a success.
 */
export function parseApiError(err, fallback = 'Something went wrong. Please try again.') {
  const status = err?.response?.status ?? null
  const data = err?.response?.data

  if (!err?.response) {
    return { message: 'Network error. Please check your connection and try again.', fieldErrors: {}, code: null, status }
  }
  if (status === 429) {
    return { message: 'Too many attempts. Please wait a moment and try again.', fieldErrors: {}, code: 'throttled', status }
  }
  if (!data || typeof data !== 'object') {
    return { message: fallback, fieldErrors: {}, code: null, status }
  }

  const container = data.details && typeof data.details === 'object' ? data.details : data
  const fieldErrors = {}
  const collect = (source) => {
    for (const [key, value] of Object.entries(source)) {
      if (NON_FIELD_KEYS.has(key)) continue
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        // A nested section (e.g. collection_defaults: { expires_in_days: '...' }):
        // surface each leaf under its own key so the form can show it by the control.
        collect(value)
        continue
      }
      const message = firstMessage(value)
      if (message) fieldErrors[key] = message
    }
  }
  collect(container)

  const general =
    (typeof data.error === 'string' && data.error) ||
    firstMessage(container.non_field_errors) ||
    (typeof data.detail === 'string' && data.detail) ||
    null

  // When field messages exist, the wrapped handler's generic summary ("Invalid
  // field 'x': ...") only repeats them — leave the message empty then.
  const message =
    Object.keys(fieldErrors).length && (!general || /^Invalid (field|input)/.test(general)) ? '' : general || fallback

  return { message, fieldErrors, code: data.code ?? null, status }
}
