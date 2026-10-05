// File Location: frontend/src/hooks/usePlanUsage.js
import { useCallback, useEffect, useRef, useState } from 'react'
import { galleriesApi } from '../api/galleriesApi'

/**
 * Live plan usage from the usage endpoint (GET galleries/dashboard/stats/):
 * collections used / remaining / limit, video minutes used / limit, plan name.
 * `refresh()` re-reads it and resolves with the fresh answer (null when the
 * request failed, leaving the last known value in place) — call it after a
 * collection is created or deleted, or right before trusting a count.
 */
export function usePlanUsage() {
  const [usage, setUsage] = useState(null)
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const data = await galleriesApi.getDashboardStats()
      if (mountedRef.current) setUsage(data)
      return data
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => { mountedRef.current = false }
  }, [refresh])

  return { usage, refresh }
}
