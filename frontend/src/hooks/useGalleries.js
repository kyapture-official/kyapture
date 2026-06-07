import { useState, useEffect, useCallback, useRef } from 'react'
import { galleriesApi } from '../api/galleriesApi'
import { mockGalleries } from '../utils/mockGalleries'

// Controlled by VITE_USE_MOCK_DATA=true in your .env.local file
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

/**
 * Generates a mock UUID matching the v4 format produced by the database,
 * so downstream components behave identically in both mock and live modes.
 */
function generateMockUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/**
 * Converts a gallery title into a clean, URL-safe slug.
 * Trims surrounding whitespace, collapses special characters to hyphens,
 * and strips any leading or trailing hyphen artifacts.
 */
function slugify(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/**
 * Manages the photographer's gallery list: fetching, searching, and all
 * CRUD operations. Abstracts network mechanics and mock/live switching
 * behind a single consistent interface.
 */
export function useGalleries(initialParams = {}) {
  const [galleries,  setGalleries]  = useState([])
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState(null)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })
  const [params,     setParams]     = useState(initialParams)

  // Tracks the active AbortController so older in-flight requests can be cancelled
  const abortControllerRef = useRef(null)

  // Mutable working copy of mock seed data — spread prevents mutating the frozen singleton
  const mockDataRef = useRef(USE_MOCK_DATA ? [...mockGalleries] : null)

  /**
   * Fetches the gallery list. Aborts any previous in-flight request before
   * starting a new one, preventing stale responses from overwriting newer state.
   */
  const fetchGalleries = useCallback(async (searchParams = {}) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    setLoading(true)
    setError(null)
    setPagination({ count: 0, next: null, previous: null })

    // ── MOCK PATH ────────────────────────────────────────────────────────────
    if (USE_MOCK_DATA) {
      try {
        // Guard 1: bail immediately if the signal was already aborted before we started
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError')

        // Simulated network latency with full symmetric listener cleanup.
        // `let timer` is forward-declared so onAbort can reference it without
        // a confusing const-after-const closure dependency.
        await new Promise((resolve, reject) => {
          let timer

          const onAbort = () => {
            clearTimeout(timer)
            signal.removeEventListener('abort', onAbort)  // Symmetrical cleanup on reject path [16]
            reject(new DOMException('Aborted', 'AbortError'))
          }

          timer = setTimeout(() => {
            signal.removeEventListener('abort', onAbort)  // Symmetrical cleanup on resolve path [16]
            resolve()
          }, 400)

          signal.addEventListener('abort', onAbort)
        })

        // Guard 2: bail if the signal aborted during the timeout window
        if (signal.aborted) return

        let results = [...mockDataRef.current]
        if (searchParams.search) {
          const query = searchParams.search.toLowerCase()
          results = results.filter((g) => g.title.toLowerCase().includes(query))
        }

        setGalleries(results)
        setPagination({ count: results.length, next: null, previous: null })
        setLoading(false)
      } catch (err) {
        if (err.name === 'AbortError') return
        setError('Failed to retrieve your collections.')
        setLoading(false)
      }
      return
    }

    // ── LIVE API PATH ────────────────────────────────────────────────────────
    try {
      const data = await galleriesApi.getGalleries(searchParams, signal)
      setGalleries(data.results)
      setPagination({
        count:    data.count,
        next:     data.next,
        previous: data.previous,
      })
    } catch (err) {
      // Silently drop responses superseded by a newer request
      if (err.name === 'CanceledError' || err.name === 'AbortError') return
      setError(err.response?.data?.detail || 'Failed to retrieve your collections.')
    } finally {
      // Only clear loading if this request wasn't cancelled mid-flight
      if (!signal.aborted) setLoading(false)
    }
  }, [])

  // Abort any lingering request on unmount to prevent state updates on dead components
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [])

  // Re-fetch whenever search/filter params change
  useEffect(() => {
    fetchGalleries(params)
  }, [params, fetchGalleries])

  /**
   * Creates a new gallery and optimistically prepends it to the list.
   */
  const createGallery = async (galleryData) => {
    setError(null)
    try {
      let newGallery

      if (USE_MOCK_DATA) {
        newGallery = {
          id:              generateMockUUID(),
          title:           galleryData.title,
          slug:            slugify(galleryData.title),
          branding_color:  galleryData.branding_color  ?? '#000000',
          is_downloadable: galleryData.is_downloadable ?? false,
          is_published:    false,
          is_active:       true,
          has_password:    false,
          cover_url:       null,
          photo_count:     0,
          created_at:      new Date().toISOString(),
          updated_at:      new Date().toISOString(),
        }
        mockDataRef.current = [newGallery, ...mockDataRef.current]
      } else {
        newGallery = await galleriesApi.createGallery(galleryData)
      }

      setGalleries((prev) => [newGallery, ...prev])
      setPagination((prev) => ({ ...prev, count: prev.count + 1 }))
      return newGallery
    } catch (err) {
      const msg =
        err.response?.data?.title?.[0] ||
        err.response?.data?.detail     ||
        err.message                    ||
        'Failed to create collection.'
      setError(msg)
      throw new Error(msg)
    }
  }

  /**
   * Updates an existing gallery's fields and merges the result into the list.
   */
  const updateGallery = async (slug, updatedFields) => {
    setError(null)
    try {
      let updated

      if (USE_MOCK_DATA) {
        const existing = mockDataRef.current.find((g) => g.slug === slug)
        updated = { ...existing, ...updatedFields, updated_at: new Date().toISOString() }
        mockDataRef.current = mockDataRef.current.map((g) => g.slug === slug ? updated : g)
      } else {
        updated = await galleriesApi.updateGallery(slug, updatedFields)
      }

      setGalleries((prev) =>
        prev.map((g) =>
          g.slug === slug ? { ...g, ...updatedFields, updated_at: updated.updated_at } : g
        )
      )
      return updated
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.message                ||
        'Failed to update gallery settings.'
      setError(msg)
      throw new Error(msg)
    }
  }

  /**
   * Deletes a gallery and removes it from the list immediately.
   */
  const deleteGallery = async (slug) => {
    setError(null)
    try {
      if (USE_MOCK_DATA) {
        mockDataRef.current = mockDataRef.current.filter((g) => g.slug !== slug)
      } else {
        await galleriesApi.deleteGallery(slug)
      }

      setGalleries((prev) => prev.filter((g) => g.slug !== slug))
      setPagination((prev) => ({ ...prev, count: Math.max(0, prev.count - 1) }))
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to delete the collection.'
      setError(msg)
      throw err
    }
  }

  /**
   * Toggles a gallery's published visibility state.
   */
  const publishGallery = async (slug, isPublished) => {
    setError(null)
    try {
      let updated

      if (USE_MOCK_DATA) {
        mockDataRef.current = mockDataRef.current.map((g) =>
          g.slug === slug ? { ...g, is_published: isPublished } : g
        )
        updated = mockDataRef.current.find((g) => g.slug === slug)
      } else {
        updated = await galleriesApi.publishGallery(slug, isPublished)
      }

      setGalleries((prev) =>
        prev.map((g) => (g.slug === slug ? { ...g, is_published: isPublished } : g))
      )
      return updated
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to update publishing visibility.'
      setError(msg)
      throw err
    }
  }

  /**
   * Sets or clears the password on a gallery, updating the has_password marker inline.
   */
  const setGalleryPassword = async (slug, password) => {
    setError(null)
    try {
      let response

      if (USE_MOCK_DATA) {
        const hasPassword = Boolean(password)
        mockDataRef.current = mockDataRef.current.map((g) =>
          g.slug === slug ? { ...g, has_password: hasPassword } : g
        )
        response = { has_password: hasPassword }
      } else {
        response = await galleriesApi.setGalleryPassword(slug, password)
      }

      setGalleries((prev) =>
        prev.map((g) =>
          g.slug === slug ? { ...g, has_password: response.has_password } : g
        )
      )
      return response
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to modify password protection.'
      setError(msg)
      throw err
    }
  }

  return {
    galleries,
    loading,
    error,
    pagination,
    setParams,
    refetch: fetchGalleries,
    createGallery,
    updateGallery,
    deleteGallery,
    publishGallery,
    setGalleryPassword,
  }
}