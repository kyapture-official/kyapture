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

/**
 * WHAT: Short relative time ("just now", "5 min ago", "3 h ago", "2 d ago"),
 *       falling back to a date for anything older than a week.
 */
export const timeAgo = (value) => {
  const then = new Date(value).getTime()
  if (!Number.isFinite(then)) return ''
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} d ago`
  return new Date(then).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** WHAT: Date plus time, e.g. "Oct 3, 2026, 2:41 PM" — for activity rows where the time matters. */
export const formatDateTime = (value) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
