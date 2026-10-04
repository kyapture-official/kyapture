// File Location: frontend/src/utils/downloadFlow.js
//
// The decisions behind the standalone download pages (Page 1 email/PIN, Page 2
// Choose Photos). Pure functions, no React, so they are unit-tested. They only
// PRESENT what the server's effective policy says — the server still enforces
// every one of these rules on each request.

// 1R.6: a client is only ever offered these two sizes. "High Resolution" resolves
// server-side to the 3600px master (or a Pro photographer's true original); the
// word "Original" is never shown to a client.
export const SIZE_OPTIONS = [
  { value: 'download', label: 'High Resolution' },
  { value: 'web', label: 'Web Size' },
]

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** What this visitor still has to give. A remembered, unexpired access token covers both. */
export function gateNeeds({ policy, hasPin, access }) {
  const earned = Boolean(access?.token) && access.expiresAt > Date.now()
  const requiresEmail = policy?.require_email !== false
  const needsEmail = requiresEmail && !earned
  const needsPin = Boolean(hasPin) && !earned
  return { needsEmail, needsPin, needsGate: needsEmail || needsPin }
}

/** Which page comes first: Page 1 when something is owed, else straight to Page 2. */
export function initialStep({ needsGate }) {
  return needsGate ? 'auth' : 'choose'
}

/** Page 1 sentence — the PIN part appears only when a Download PIN is enabled. */
export function gateIntro({ needsEmail, needsPin, studio }) {
  const emailPart = 'Your email will be used to notify you when the files are ready for download.'
  const pinPart = `Please enter the download PIN provided by ${studio || 'your photographer'} to download this photo collection.`
  if (needsEmail && needsPin) return `${emailPart} ${pinPart}`
  return needsPin ? pinPart : emailPart
}

/** Size radios: only what the photographer enabled, in High Resolution -> Web Size order. */
export function sizeOptions(policy) {
  const allowed = Array.isArray(policy?.allowed_sizes) ? policy.allowed_sizes : []
  const options = SIZE_OPTIONS.filter((option) => allowed.includes(option.value))
  return options.length ? options : SIZE_OPTIONS
}

/** High Resolution unless it is switched off; a single option is simply preselected. */
export function defaultSize(options) {
  return (options.find((option) => option.value === 'download') || options[0]).value
}

/**
 * "Choose Photos": which checkboxes exist.
 *   unrestricted  every set, "All photos" = the whole gallery
 *   restricted    only the sets enabled in Download > Advanced, "All photos" = those sets
 * Sets with no ready photos are left out (nothing to download).
 */
export function scopeModel({ policy, photoSets = [], photoCount = 0 }) {
  const enabled = Array.isArray(policy?.sets_enabled) ? policy.sets_enabled.map(String) : null
  const sets = photoSets
    .filter((set) => (set.photo_count ?? 0) > 0)
    .filter((set) => !enabled || enabled.includes(String(set.id)))
    .map((set) => ({ id: String(set.id), name: set.name, photo_count: set.photo_count ?? 0 }))
  const wholeGallery = !enabled
  const allCount = wholeGallery ? photoCount : sets.reduce((sum, set) => sum + set.photo_count, 0)
  return { sets, wholeGallery, allCount }
}

/** "1 photo" / "6 photos". */
export function photoLabel(count) {
  return `${count} ${count === 1 ? 'photo' : 'photos'}`
}

export function allSetIds(model) {
  return model.sets.map((set) => set.id)
}

/** "All photos" is on exactly when every set is on (always on for a gallery with no sets). */
export function isAllSelected(model, selected) {
  return model.sets.every((set) => selected.includes(set.id))
}

export function toggleAll(model, selected) {
  return isAllSelected(model, selected) ? [] : allSetIds(model)
}

export function toggleSet(selected, id) {
  return selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]
}

/**
 * The API selection for the current checkboxes, or null when nothing is chosen.
 *   whole gallery        {}                (no set_id: the server packages everything)
 *   exactly one set      { setId }
 *   several sets         { setIds }
 */
export function selectionRequest(model, selected) {
  if (!model.sets.length) return model.wholeGallery ? {} : null
  const chosen = allSetIds(model).filter((id) => selected.includes(id))
  if (!chosen.length) return null
  if (model.wholeGallery && chosen.length === model.sets.length) return {}
  return chosen.length === 1 ? { setId: chosen[0] } : { setIds: chosen }
}

const BLOCKED_CODES = ['download_limit_reached', 'pin_limit_reached', 'email_not_authorized', 'set_not_enabled']

export function isBlockedCode(code) {
  return BLOCKED_CODES.includes(code)
}

/**
 * Friendly wording for a blocked download. Built from the code so it reads the
 * same whichever endpoint refused; the photographer's contact list is never part
 * of any message.
 */
export function blockedMessage(code, studio, fallback = '') {
  const who = studio || 'the photographer'
  switch (code) {
    case 'download_limit_reached':
    case 'pin_limit_reached':
      return `Download limit reached. Contact ${who}.`
    case 'email_not_authorized':
      return `This email is not authorized to download. Contact ${who}.`
    case 'set_not_enabled':
      return 'That part of the gallery is not available for download.'
    default:
      return fallback
  }
}

// ── Pages 3 and 4: preparing / ready ────────────────────────────────────────

/** The prepared download's own page. The key is bound to that one job (no email / PIN asked again). */
export function jobPagePath(username, slug, jobId, key) {
  const base = `/g/${encodeURIComponent(username)}/${encodeURIComponent(slug)}/download/file/${encodeURIComponent(jobId)}`
  return key ? `${base}?key=${encodeURIComponent(key)}` : base
}

/** Wait before status check number `attempt` (0-based, the first check itself is immediate): 2s, 5s, then every 10s. */
export function pollDelay(attempt) {
  const delays = [2000, 5000, 10000]
  return delays[Math.min(Math.max(attempt, 0), delays.length - 1)]
}

/** "89.6 MB", "1.9 GB" — never "0 MB" for a real file. */
export function formatBytes(bytes) {
  const value = Number(bytes) || 0
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(value / 1024))} KB`
}

// A prepared download that is gone (7 days passed, purged, or never was) and one
// that failed to build are different messages; everything else is a hiccup to retry.
const EXPIRED_CODES = ['download_expired', 'download_not_found', 'file_missing', 'file_unavailable']

/**
 * What a status answer or a status error means for the page:
 *   'preparing' | 'ready' | 'expired' | 'failed' | 'locked' | 'retry'
 */
export function jobViewFor({ data = null, error = null } = {}) {
  if (error) {
    if (EXPIRED_CODES.includes(error.code)) return 'expired'
    if (error.status === 401 || error.code === 'session_required') return 'locked'
    return 'retry'
  }
  if (data?.state === 'ready') return 'ready'
  if (data?.state === 'preparing') return 'preparing'
  if (data?.state === 'failed') return EXPIRED_CODES.includes(data.code) ? 'expired' : 'failed'
  return 'retry'
}
