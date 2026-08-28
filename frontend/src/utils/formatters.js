// WHERE: frontend/src/utils/formatters.js
// WHAT: Standardized string, byte, currency, and date parsing utilities.

/**
 * Parses and formats raw byte integers into human-readable data bounds.
 * Prevents crash anomalies if negative storage thresholds are calculated.
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
 * Guarded against parsing empty values or malformed dates (e.g., 'Invalid Date').
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
 * Renders correctly as 'NPR 1,50,000' (Nepali comma grouping) instead of Western '150,000'.
 */
export const formatCurrency = (amount) => {
  const numericAmount = Number(amount)
  if (isNaN(numericAmount)) return 'NPR 0'
  return `NPR ${numericAmount.toLocaleString('en-NP')}`
}

/**
 * Converts any date-ish string or ISO timestamp into a safe 'YYYY-MM-DD' input string.
 * Rejects invalid strings, null, or empty data, returning an empty string to keep inputs controlled.
 */
export const toDateInputValue = (value) => {
  if (!value) return ''
  const datePart = String(value).split('T')[0]
  return /^\d{4}-\d{2}-\d{2}$/.test(datePart) ? datePart : ''
}