// File Location: frontend/src/components/settings/useUserSettings.js
import { useCallback, useEffect, useRef, useState } from 'react'
import { authApi } from '../../api/authApi'
import { parseApiError } from '../../utils/apiErrors'

/**
 * WHAT: Loads the persisted notification / privacy / collection-default
 *       settings and saves changes through PATCH /auth/settings/.
 * WHY:  The UI must always show what the BACKEND holds. `settings` is only ever
 *       set from a server response (initial GET or a successful PATCH), never
 *       optimistically guessed, so a refresh can't disagree with what's shown.
 */
export function useUserSettings() {
  const isMountedRef = useRef(true)
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const data = await authApi.getSettings()
      if (isMountedRef.current) setSettings(data)
    } catch (err) {
      if (isMountedRef.current) setLoadError(parseApiError(err, 'Could not load your settings.').message)
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  /** Resolves with the saved settings; rejects with a normalized { message, fieldErrors, code }. */
  const save = useCallback(async (patch) => {
    try {
      const saved = await authApi.updateSettings(patch)
      if (isMountedRef.current) setSettings(saved)
      return saved
    } catch (err) {
      throw parseApiError(err, 'Could not save your settings.')
    }
  }, [])

  return { settings, loading, loadError, reload: load, save }
}
