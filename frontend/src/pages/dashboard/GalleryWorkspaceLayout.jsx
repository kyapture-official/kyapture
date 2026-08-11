// frontend/src/pages/dashboard/GalleryWorkspaceLayout.jsx
import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Outlet } from 'react-router-dom'
import { galleriesApi } from '../../api/galleriesApi'
import { mockGalleries } from '../../utils/mockGalleries'
import Spinner from '../../components/ui/Spinner'
import CollectionSidebar from '../../components/layout/CollectionSidebar'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

export default function GalleryWorkspaceLayout() {
  const { id } = useParams()      // holds the gallery SLUG
  const navigate = useNavigate()

  const [gallery, setGallery]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [publishUpdating, setPublishUpdating] = useState(false)
  const [copied, setCopied]         = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)

  const isMountedRef    = useRef(false)
  const copyTimeoutRef  = useRef(null)
  const skipNextLoadRef = useRef(false)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  useEffect(() => {
    async function loadGallery() {
      if (skipNextLoadRef.current) {
        skipNextLoadRef.current = false
        setLoading(false)
        return
      }

      setLoading(true)
      setErrorMsg('')

      if (USE_MOCK_DATA) {
        setTimeout(() => {
          const match = mockGalleries.find((g) => g.slug === id)
          if (!isMountedRef.current) return
          if (!match) setErrorMsg('Collection not found.')
          else setGallery(match)
          setLoading(false)
        }, 300)
        return
      }

      try {
        const data = await galleriesApi.getGallery(id)
        if (isMountedRef.current) setGallery(data)
      } catch (err) {
        if (isMountedRef.current) {
          setErrorMsg(err.response?.data?.detail || 'Failed to retrieve collection configurations.')
        }
      } finally {
        if (isMountedRef.current) setLoading(false)
      }
    }

    loadGallery()
  }, [id])

  const handleTogglePublish = async () => {
    if (publishUpdating || !gallery) return
    setPublishUpdating(true)
    setErrorMsg('')
    const nextState = !gallery.is_published

    try {
      if (USE_MOCK_DATA) {
        setGallery((prev) => ({ ...prev, is_published: nextState }))
      } else {
        await galleriesApi.publishGallery(id, nextState)
        setGallery((prev) => ({ ...prev, is_published: nextState }))
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to update publication status.')
      }
    } finally {
      if (isMountedRef.current) setPublishUpdating(false)
    }
  }

  const handleCopyLink = async () => {
    if (!gallery) return
    const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'
    const clientURL = `${window.location.protocol}//${window.location.host}/g/${ownerUsername}/${gallery.slug}`

    try {
      await navigator.clipboard.writeText(clientURL)
      setCopied(true)
      setCopyFailed(false)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyFailed(true)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopyFailed(false), 2000)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream-50">
        <Spinner size="lg" />
      </div>
    )
  }

  if (errorMsg && !gallery) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-cream-50 px-6 text-center gap-4">
        <p className="text-sm text-red-600">{errorMsg}</p>
        <button onClick={() => navigate('/dashboard/galleries')} className="text-sm font-semibold text-ink hover:underline">
          ← Back to Collections
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-cream-50">

      {/* LEFT — replaces the global dashboard nav entirely for this page */}
      <CollectionSidebar gallery={gallery} />

      {/* RIGHT — top bar + routed Photos/Settings content */}
      <div className="flex-1 min-w-0">
        <div className="sticky top-0 z-20 bg-cream-50/90 backdrop-blur-sm border-b border-cream-200">
          <div className="max-w-5xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-muted">
              <button onClick={() => navigate('/dashboard/galleries')} className="hover:text-ink hover:underline">
                Collections
              </button>
              <span className="text-cream-300">/</span>
              <span className="font-semibold text-ink">{gallery.title}</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCopyLink}
                className="px-3.5 py-2 border border-cream-300 text-ink/80 hover:text-ink bg-white hover:bg-cream-50 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm"
              >
                {copied ? 'Copied! ✓' : copyFailed ? 'Copy failed ✗' : 'Share Link'}
              </button>

              <button
                type="button"
                onClick={handleTogglePublish}
                disabled={publishUpdating}
                className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm ${
                  gallery.is_published
                    ? 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100'
                    : 'bg-ink text-white hover:opacity-90'
                }`}
              >
                {gallery.is_published ? 'Published' : 'Publish Collection'}
              </button>
            </div>
          </div>
        </div>

        {errorMsg && (
          <div className="max-w-5xl mx-auto px-6 pt-4">
            <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
              {errorMsg}
            </div>
          </div>
        )}

        <div className="max-w-5xl mx-auto px-6 py-8">
          <Outlet context={{ gallery, setGallery, slug: id, skipNextLoadRef, navigate, isMountedRef }} />
        </div>
      </div>
    </div>
  )
}