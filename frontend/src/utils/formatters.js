// WHERE: frontend/src/utils/formatters.js

/**
 * Parses and formats raw byte integers into human-readable data bounds.
 */
export const formatBytes = (bytes) => {
  const numericBytes = Number(bytes)
  if (isNaN(numericBytes) || numericBytes <= 0) return '0 B'
  if (numericBytes < 1024) return `${numericBytes} B`
  if (numericBytes < 1024 * 1024) return `${(numericBytes / 1024).toFixed(1)} KB`
  if (numericBytes < 1024 * 1024 * 1024) return `${(numericBytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(numericBytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/**
 * Standardizes localized readable presentation dates.
 */
export const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const parsedDate = new Date(dateStr)
  if (isNaN(parsedDate.getTime())) return ''
  
  return parsedDate.toLocaleDateString('en-US', {
    year: 'numeric', 
    month: 'short', 
    day: 'numeric',
  })
}

/**
 * Localizes currency values to Nepali Rupee standard (en-NP format).
 */
export const formatCurrency = (amount) => {
  const numericAmount = Number(amount)
  if (isNaN(numericAmount)) return 'NPR 0'
  return `NPR ${numericAmount.toLocaleString('en-NP')}`
}

/**
 * Converts any date-ish string or ISO timestamp into a safe 'YYYY-MM-DD' input string.
 */
export const toDateInputValue = (value) => {
  if (!value) return ''
  const datePart = String(value).split('T')[0]
  return /^\d{4}-\d{2}-\d{2}$/.test(datePart) ? datePart : ''
}

/**
 * WHAT: Isomorphic Absolute URL Generator
 * WHY:  Dynamic link generator that returns the canonical same-origin gallery
 *       path in every environment.
 */
// Locked product decision: the MVP client gallery URL is path-based only —
// /g/:username/:slug — everywhere, including production. Wildcard subdomain
// galleries (username.domain.tld) are explicitly post-MVP (no wildcard DNS/
// TLS/routing infrastructure exists for them yet); this must stay
// path-based until that infrastructure is actually built. See
// docs/KYAPTURE_PRODUCT_DECISIONS.md #3-4.
export const buildClientGalleryUrl = (username, slug) => {
  if (!username || !slug) return ''

  if (typeof window !== 'undefined') {
    // Same-origin path build — correct in dev, staging, and production
    // alike, and immune to VITE_APP_DOMAIN drifting from the real origin.
    return `${window.location.origin}/g/${username}/${slug}`
  }

  return `/g/${username}/${slug}`
}

/**
 * WHAT: Media Playback Duration Formatter
 * WHY:  Parses raw duration integers/floats (seconds) into standard MM:SS or H:MM:SS format
 *       defensively, preventing NaN outputs on empty, negative, or invalid data.
 */
export const formatDuration = (seconds) => {
  const num = Number(seconds)
  if (isNaN(num) || num < 0) return '00:00'
  
  const hrs = Math.floor(num / 3600)
  const mins = Math.floor((num % 3600) / 60)
  const secs = Math.floor(num % 60)

  const formattedMins = hrs > 0 ? String(mins).padStart(2, '0') : String(mins)
  const formattedSecs = String(secs).padStart(2, '0')

  if (hrs > 0) {
    return `${hrs}:${formattedMins}:${formattedSecs}`
  }
  return `${formattedMins}:${formattedSecs}`
}
