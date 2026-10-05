// frontend/src/hooks/usePlans.js
import { useEffect, useState } from 'react'
import { subscriptionsApi } from '../api/subscriptionsApi'

// Plans are owner-editable data (Django admin), so nothing about them is
// cached across page loads: each mount asks the API. Concurrent mounts on one
// screen (e.g. several locked-feature banners) share a single in-flight request.
let inflight = null
function fetchPlansOnce() {
  if (!inflight) {
    inflight = subscriptionsApi.getPlans()
      .then((data) => data?.results || data || [])
      .finally(() => { inflight = null })
  }
  return inflight
}

export function usePlans() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    fetchPlansOnce()
      .then((list) => { if (alive) setPlans(list) })
      .catch(() => { /* locked-feature copy falls back to generic wording */ })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  return { plans, loading }
}

/** Cheapest plan (plans arrive ordered by price) that includes the feature, or null. */
export function requiredPlan(plans, featureKey) {
  return plans.find((p) => p.features?.some((f) => f.key === featureKey && f.included)) || null
}

export function featureLabel(plans, featureKey) {
  for (const p of plans) {
    const row = p.features?.find((f) => f.key === featureKey)
    if (row) return row.label
  }
  return ''
}
