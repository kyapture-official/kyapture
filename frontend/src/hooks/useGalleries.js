import { useState, useEffect, useCallback } from 'react'
import { galleriesApi } from '../api/galleriesApi'

export function useGalleries() {
  const [galleries, setGalleries] = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    galleriesApi.list()
      .then((r) => setGalleries(r.data.results || r.data))
      .catch((e) => setError(e))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  return { galleries, loading, error, reload: load }
}
