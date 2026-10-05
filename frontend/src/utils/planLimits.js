// File Location: frontend/src/utils/planLimits.js
// Display formatting for plan limits. Every number comes from the plans API
// (the plan table); nothing here knows a plan, price or limit. Limits that are
// null/undefined mean "Unlimited".

import { formatBytes } from './formatters.js'

const num = (n) => Number(n).toLocaleString('en-NP')

export const formatStorage = (gb) => `${num(gb)} GB`

const MB = 1024 ** 2

/**
 * "2.99 GB / 3 GB" from the usage endpoint. Used is read in bytes so a small account
 * shows MB; from 1000 MB up it reads in GB (never "1024.0 MB" just under a full GB).
 */
export const formatStorageUsage = (usage) => {
  const bytes = Number(usage.storage_used_bytes)
  const used = bytes >= 1000 * MB ? `${(bytes / 1024 ** 3).toFixed(2)} GB` : formatBytes(bytes)
  return `${used} / ${formatStorage(usage.plan_storage_limit_gb)}`
}

/** "2.99 / 3 GB": the figures a storage refusal carries (already in GB). */
export const formatStorageFigures = (usedGb, limitGb) =>
  `${Number(usedGb).toLocaleString('en-NP', { maximumFractionDigits: 2 })} / ${num(limitGb)} GB`

/** Collections cap: a bare number, or "Unlimited" when the plan has none. */
export const formatCollections = (max) => (max == null ? 'Unlimited' : num(max))

/**
 * Photo estimate under a plan's storage: "1,000+ photos". The figure and the
 * average photo size are computed by the backend (estimated_photos); this only
 * formats it.
 */
export const formatPhotoEstimate = (plan) =>
  plan?.estimated_photos == null ? '' : `${num(plan.estimated_photos)}+ photos`

/** Video allowance: 0 = none ("—"), empty = "Unlimited", else "30 min" / "1 hour" / "2 hours". */
export const formatVideoMinutes = (minutes) => {
  if (minutes == null) return 'Unlimited'
  const m = Number(minutes)
  if (!m) return '—'
  if (m < 60) return `${m} min`
  const hours = Math.floor(m / 60)
  const rest = m % 60
  const hourText = `${hours} ${hours === 1 ? 'hour' : 'hours'}`
  return rest ? `${hourText} ${rest} min` : hourText
}
