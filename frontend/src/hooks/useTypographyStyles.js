// frontend/src/hooks/useTypographyStyles.js

import { useCallback, useEffect, useState } from 'react'
import { galleriesApi } from '../api/galleriesApi'

// The six styles are static server constants, so one successful answer is kept
// for the whole session and shared by the Design page, Collection Defaults and
// the dashboard Preview. A failed request is not cached (Retry asks again).
let cached = null
let inFlight = null

function loadStyles() {
  if (cached) return Promise.resolve(cached)
  if (!inFlight) {
    inFlight = galleriesApi
      .getTypographyStyles()
      .then((data) => {
        cached = Array.isArray(data?.styles) ? data.styles : []
        return cached
      })
      .finally(() => { inFlight = null })
  }
  return inFlight
}

/** { styles, loading, error, retry } — `styles` is [] until the server answers. */
export function useTypographyStyles() {
  const [styles, setStyles] = useState(cached || [])
  const [loading, setLoading] = useState(!cached)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    if (cached) {
      setStyles(cached)
      setLoading(false)
      return undefined
    }
    setLoading(true)
    setError(null)
    loadStyles()
      .then((list) => { if (active) setStyles(list) })
      .catch(() => { if (active) setError('Could not load the typography styles.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return { styles, loading, error, retry }
}
