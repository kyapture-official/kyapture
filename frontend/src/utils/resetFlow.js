// frontend/src/utils/resetFlow.js
/**
 * Pure helpers for the "forgot password" pages (7-C). No React, no network,
 * so they run under `node --test`.
 *
 * The emailed link is `/reset-password#token=<43 url-safe chars>`. The token
 * lives in the URL fragment, which a browser never sends to any server. The
 * page reads it once with `readResetToken`, then removes it from the address
 * bar and history (`history.replaceState`) and only ever sends it in a POST body.
 */

const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/

/** The token from a location hash like "#token=abc", or '' when there is none or it is malformed. */
export function readResetToken(hash) {
  if (typeof hash !== 'string' || !hash) return ''
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const token = params.get('token') || ''
  return TOKEN_RE.test(token) ? token : ''
}

function firstMessage(value) {
  if (Array.isArray(value)) return value.length ? String(value[0]) : ''
  return typeof value === 'string' ? value : ''
}

function allMessages(value) {
  if (Array.isArray(value)) return value.map(String)
  return typeof value === 'string' && value ? [value] : []
}

/**
 * Maps a failed check/confirm call to what the reset page shows:
 *   { kind: 'invalid' }                         the link is unknown, expired, used or replaced
 *   { kind: 'fields', password: [...], confirm } the new password was refused (link still usable)
 *   { kind: 'throttled', message }              too many tries from this network
 *   { kind: 'error', message }                  anything else (network, 5xx)
 */
export function resetErrorState(err) {
  const status = err?.response?.status
  const data = err?.response?.data || {}
  if (status === 400 && data.code === 'reset_link_invalid') return { kind: 'invalid' }
  if (status === 400 && (data.new_password || data.new_password2)) {
    return {
      kind: 'fields',
      password: allMessages(data.new_password),
      confirm: firstMessage(data.new_password2),
    }
  }
  if (status === 429) {
    return { kind: 'throttled', message: 'Too many attempts from this network. Wait a while, then try again.' }
  }
  return { kind: 'error', message: 'Something went wrong. Check your connection and try again.' }
}

/** The message the forgot page shows for a failed request. */
export function forgotErrorMessage(err) {
  const status = err?.response?.status
  const data = err?.response?.data || {}
  if (status === 400 && data.code === 'email_invalid') return 'Enter a valid email address.'
  if (status === 429) return 'Too many reset requests from this network. Wait a while, then try again.'
  return 'Something went wrong. Check your connection and try again.'
}
