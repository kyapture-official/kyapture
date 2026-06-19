import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { galleriesApi } from '../../api/galleriesApi'
import { photosApi } from '../../api/photosApi'
import { mockGalleries } from '../../utils/mockGalleries'
import Spinner from '../../components/ui/Spinner'
import DropZone from '../../components/ui/DropZone'
import PhotoGrid from '../../components/shared/PhotoGrid'
import PhotoLightbox from '../../components/shared/PhotoLightbox'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

/**
 * WHAT: Gallery Detail Management Page
 * WHY:  Coordinates individual gallery settings, password controls, download access,
 *       and provides a fully unified, live-updating photo upload and sorting dashboard.
 */
export default function GalleryDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [gallery, setGallery] = useState(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [updating, setUpdating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)

  // ── PHOTO-MANAGEMENT STATES ──
  const [photos, setPhotos] = useState([])
  const [uploadQueue, setUploadQueue] = useState([])
  const [lightboxIndex, setLightboxIndex] = useState(null) // Tracks currently open fullscreen photo

  // Local Form States
  const [title, setTitle] = useState('')
  const [brandingColor, setBrandingColor] = useState('#000000')
  const [isDownloadable, setIsDownloadable] = useState(false)
  const [password, setPassword] = useState('')
  const [hasPassword, setHasPassword] = useState(false)

  const isMountedRef = useRef(false)
  const copyTimeoutRef = useRef(null)
  const skipNextLoadRef = useRef(false)
  const uploadQueueRef = useRef([]) // Mirrors `uploadQueue` so unmount cleanup always sees the latest value
  const activeTimersRef = useRef(new Set()) // Tracks in-flight mock-upload intervals so they can be cleared on unmount

  // Keep the ref in sync without re-running the mount/unmount effect below.
  useEffect(() => {
    uploadQueueRef.current = uploadQueue
  }, [uploadQueue])

  // Mount/unmount lifecycle — runs exactly ONCE.
  // Cleanup only fires on actual unmount to prevent premature blob revoking.
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)

      // Stop any simulated/in-flight upload timers so they don't keep ticking after unmount.
      activeTimersRef.current.forEach((timerId) => clearInterval(timerId))
      activeTimersRef.current.clear()

      // Only release blobs for uploads that never finished. Anything already promoted
      // into `photos` must keep its URL alive for as long as it's being displayed.
      uploadQueueRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    }
  }, [])

  /**
   * Syncs the parent gallery configurations and local form inputs in a single thread.
   * Defaults guard against undefined fields silently turning inputs into uncontrolled ones.
   */
  const syncFormFromGallery = (data) => {
    setGallery(data)
    setTitle(data.title ?? '')
    setBrandingColor(data.branding_color || '#000000')
    setIsDownloadable(Boolean(data.is_downloadable))
    setHasPassword(Boolean(data.has_password))
  }

  // ── DATA LOADING LIFE-CYCLE ───────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false // Guards against a stale response overwriting a newer one if `id` changes quickly

    async function loadGallery() {
      if (skipNextLoadRef.current) {
        skipNextLoadRef.current = false
        setLoading(false)
        return
      }

      setLoading(true)
      setErrorMsg('')

      if (USE_MOCK_DATA) {
        await new Promise((resolve) => setTimeout(resolve, 300))
        if (cancelled || !isMountedRef.current) return

        const match = mockGalleries.find((g) => g.slug === id)
        if (!match) {
          setErrorMsg('Collection not found.')
          setLoading(false)
          return
        }

        syncFormFromGallery(match)

        // Seed mock photos dynamically inside our mock portfolios
        setPhotos(match.slug === 'mila-portraits' ? [
          { id: 'mock-img-1', image_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=800&q=80', original_name: 'portrait_studio_01.jpg' },
          { id: 'mock-img-2', image_url: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=800&q=80', original_name: 'portrait_studio_02.jpg' }
        ] : [])

        setLoading(false)
        return
      }

      try {
        const data = await galleriesApi.getGallery(id)
        if (cancelled || !isMountedRef.current) return
        syncFormFromGallery(data)
        setPhotos(data.photos || [])
      } catch (err) {
        if (cancelled || !isMountedRef.current) return
        setErrorMsg(err.response?.data?.detail || 'Failed to retrieve collection configurations.')
      } finally {
        if (!cancelled && isMountedRef.current) {
          setLoading(false)
        }
      }
    }

    loadGallery()

    return () => {
      cancelled = true
    }
  }, [id])

  // ── PHOTO UPLOAD ACTION ───────────────────────────────────────────────────

  // Mock-only: animate a fake progress bar since there's no real backend to talk to.
  const simulateMockUpload = useCallback((item) => {
    const timerId = setInterval(() => {
      if (!isMountedRef.current) {
        clearInterval(timerId)
        activeTimersRef.current.delete(timerId)
        return
      }

      setUploadQueue((prev) => {
        const current = prev.find((q) => q.id === item.id)
        if (!current) {
          clearInterval(timerId)
          activeTimersRef.current.delete(timerId)
          return prev
        }

        const nextProgress = Math.min(100, current.progress + Math.floor(Math.random() * 15) + 5)

        if (nextProgress >= 100) {
          clearInterval(timerId)
          activeTimersRef.current.delete(timerId)
          // Move item from upload queue to the completed photos grid.
          setPhotos((prevPhotos) => [
            ...prevPhotos,
            { id: item.id, image_url: item.previewUrl, original_name: item.file.name },
          ])
          return prev.filter((q) => q.id !== item.id)
        }

        return prev.map((q) => (q.id === item.id ? { ...q, progress: nextProgress } : q))
      })
    }, 300)

    activeTimersRef.current.add(timerId)
  }, [])

  /**
   * WHAT: S3 Bulk Upload Handler
   * WHY:  uploadBulk is a batch endpoint — it accepts many files in a single
   *       multipart request. This batches every file from one selection/drop
   *       into a single call and maps the response to the queue items [18].
   */
  const uploadFilesToServer = useCallback((queueItems) => {
    const formData = new FormData()
    queueItems.forEach((item) => formData.append('images', item.file))

    const idsInBatch = new Set(queueItems.map((item) => item.id))

    photosApi
      .uploadBulk(id, formData, (percent) => {
        if (!isMountedRef.current) return
        // One combined request -> one shared progress value for every item in this batch
        setUploadQueue((prev) =>
          prev.map((q) => (idsInBatch.has(q.id) ? { ...q, progress: percent } : q))
        )
      })
      .then((savedPhotos) => {
        if (!isMountedRef.current) return

        // Symmetrical cleanup: drop local memory blob links on successful S3 upload
        queueItems.forEach((item) => URL.revokeObjectURL(item.previewUrl))
        setPhotos((prev) => [...prev, ...(savedPhotos || [])])
        setUploadQueue((prev) => prev.filter((q) => !idsInBatch.has(q.id)))
      })
      .catch((err) => {
        if (!isMountedRef.current) return

        queueItems.forEach((item) => URL.revokeObjectURL(item.previewUrl))
        setUploadQueue((prev) => prev.filter((q) => !idsInBatch.has(q.id)))

        const label = queueItems.length === 1
          ? `"${queueItems[0].file.name}"`
          : `${queueItems.length} files`
        setErrorMsg(err.response?.data?.detail || `Failed to upload ${label}.`)
      })
  }, [id])

  const handleFilesSelected = useCallback((files) => {
    if (!files.length) return

    const queueItems = files.map((file) => ({
      id: Math.random().toString(36).substring(2, 9),
      file,
      previewUrl: URL.createObjectURL(file),
      progress: 0,
    }))

    setUploadQueue((prev) => [...prev, ...queueItems])

    if (USE_MOCK_DATA) {
      queueItems.forEach((item) => simulateMockUpload(item))
    } else {
      uploadFilesToServer(queueItems)
    }
  }, [simulateMockUpload, uploadFilesToServer])

  // ── PHOTO DELETION ACTION (Symmetrical Bulk and Single) ───────────────────
  const handleDeletePhotos = useCallback(async (photoIds) => {
    setErrorMsg('')
    try {
      if (!USE_MOCK_DATA) {
        await photosApi.deletePhotos(id, photoIds)
      }

      // Symmetrical Deletion: remove targets from the local UI state array
      const idsSet = new Set(photoIds)
      setPhotos((prev) => prev.filter((photo) => !idsSet.has(photo.id)))
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to delete selected photos.')
      throw err // Re-throw to allow child grids to clear loading locks safely
    }
  }, [id])

  // ── PHOTO REORDERING ACTION ───────────────────────────────────────────────
  const handleReorderPhotos = useCallback(async (orderedPhotoIds) => {
    setErrorMsg('')
    try {
      if (!USE_MOCK_DATA) {
        await photosApi.reorderPhotos(id, orderedPhotoIds)
      }

      // Update local sorting state from the latest photos snapshot (avoids a stale closure)
      setPhotos((prev) => {
        const photoMap = new Map(prev.map((p) => [p.id, p]))
        return orderedPhotoIds.map((pid) => photoMap.get(pid)).filter(Boolean)
      })
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to save photo sorting configuration.')
      throw err // Re-throw to allow child grids to roll back state on failure
    }
  }, [id])

  // ── SETTINGS CONFIGURATION ACTIONS ────────────────────────────────────────
  const handleSaveSettings = async (e) => {
    e.preventDefault()
    if (!title.trim() || updating) return

    setUpdating(true)
    setErrorMsg('')

    const payload = {
      title: title.trim(),
      branding_color: brandingColor,
      is_downloadable: isDownloadable,
    }

    try {
      let updated
      if (USE_MOCK_DATA) {
        const mockSlug = payload.title
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-+|-+$/g, '')
        updated = { ...gallery, ...payload, slug: mockSlug }
      } else {
        updated = await galleriesApi.updateGallery(id, payload)
      }

      syncFormFromGallery(updated)

      if (updated.slug !== id) {
        skipNextLoadRef.current = true
        navigate(`/dashboard/galleries/${updated.slug}`, { replace: true })
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to save collection configurations.')
      }
    } finally {
      if (isMountedRef.current) {
        setUpdating(false)
      }
    }
  }

  const handleTogglePublish = async () => {
    if (updating || !gallery) return
    setUpdating(true)
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
      if (isMountedRef.current) {
        setUpdating(false)
      }
    }
  }

  const handleSavePassword = async (e) => {
    e.preventDefault()
    if (updating) return

    const trimmedPassword = password.trim()

    if (!trimmedPassword && !hasPassword) {
      setErrorMsg('Enter a password to enable protection.')
      return
    }

    if (!trimmedPassword && hasPassword) {
      const confirmed = window.confirm(
        'Remove password protection from this gallery? Clients will no longer need to authenticate.'
      )
      if (!confirmed) return
    }

    setUpdating(true)
    setErrorMsg('')

    try {
      if (USE_MOCK_DATA) {
        const newHasPassword = Boolean(trimmedPassword)
        setHasPassword(newHasPassword)
        setGallery((prev) => ({ ...prev, has_password: newHasPassword }))
        setPassword('')
      } else {
        const response = await galleriesApi.setGalleryPassword(id, trimmedPassword || null)
        setHasPassword(response.has_password)
        setGallery((prev) => ({ ...prev, has_password: response.has_password }))
        setPassword('')
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to update security credentials.')
      }
    } finally {
      if (isMountedRef.current) {
        setUpdating(false)
      }
    }
  }

  const handleCopyLink = async () => {
    if (!gallery) return

    const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'
    const clientURL = `${window.location.protocol}//${window.location.host}/g/${ownerUsername}/${gallery.slug}`

    const markCopied = () => {
      setCopied(true)
      setCopyFailed(false)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
    }

    const markFailed = () => {
      setCopyFailed(true)
      setCopied(false)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopyFailed(false), 2000)
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(clientURL)
      } else {
        // Fallback for browsers/contexts without the async Clipboard API (e.g. non-HTTPS).
        const textarea = document.createElement('textarea')
        textarea.value = clientURL
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(textarea)
        if (!ok) throw new Error('execCommand copy failed')
      }
      markCopied()
    } catch (err) {
      console.error('Failed to copy link:', err)
      markFailed()
    }
  }

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (errorMsg && !gallery) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 mb-6">
          {errorMsg}
        </div>
        <Link to="/dashboard/galleries" className="text-sm font-semibold text-gray-900 hover:underline">
          ← Back to galleries
        </Link>
      </div>
    )
  }

  const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeUp">
      
      {/* HEADER NAVIGATION */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-gray-200 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/dashboard/galleries" className="text-xs font-medium text-gray-500 hover:text-gray-900 hover:underline">
              Collections
            </Link>
            <span className="text-xs text-gray-300">/</span>
            <span className="text-xs font-semibold text-gray-900">{gallery.title}</span>
          </div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight font-sans">
            {gallery.title}
          </h1>
        </div>

        {/* Global Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleCopyLink}
            className="px-3.5 py-2 border border-gray-200 text-gray-700 hover:text-gray-900 bg-white hover:bg-gray-50 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm flex items-center gap-2"
          >
            {copied ? 'Copied! ✓' : copyFailed ? 'Copy failed ✗' : 'Share Link'}
          </button>

          <button
            type="button"
            onClick={handleTogglePublish}
            disabled={updating}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm ${
              gallery.is_published
                ? 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100'
                : 'bg-gray-900 text-white hover:bg-gray-800'
            }`}
          >
            {gallery.is_published ? 'Published' : 'Publish Collection'}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div role="alert" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans">
          {errorMsg}
        </div>
      )}

      {/* CENTRALIZED SETTINGS GRID */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* LEFT COLUMN: SETTINGS FORMS */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Card 1: Configuration Form */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-6 border-b border-gray-100 pb-3">
              Collection Configurations
            </h2>
            <form onSubmit={handleSaveSettings} noValidate className="space-y-6">
              
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-gray-700" htmlFor="gallery-title">
                  Gallery Title
                </label>
                <input
                  id="gallery-title"
                  type="text"
                  value={title}
                  maxLength={100}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={updating}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-100 transition-all disabled:opacity-50"
                  required
                />
              </div>

              {/* Dynamic Slug Preview — mirrors the real share-link format used by handleCopyLink */}
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-100 text-xs">
                <span className="font-semibold text-gray-400 uppercase tracking-wider block text-[10px]">
                  Live Slug Link
                </span>
                <p className="mt-1 font-semibold text-gray-600 truncate">
                  {window.location.host}/g/{ownerUsername}/
                  <span className="text-gray-900 font-bold font-mono">
                    {title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'your-slug'}
                  </span>
                </p>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-gray-700" htmlFor="gallery-color">
                  Photographer Brand Accent
                </label>
                <div className="flex items-center gap-3">
                  <input
                    id="gallery-color"
                    type="color"
                    value={brandingColor}
                    onChange={(e) => setBrandingColor(e.target.value)}
                    disabled={updating}
                    className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer overflow-hidden p-0 bg-transparent disabled:opacity-50"
                  />
                  <span className="text-xs text-gray-500 font-medium font-mono uppercase">
                    {brandingColor}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                <input
                  id="gallery-download"
                  type="checkbox"
                  checked={isDownloadable}
                  onChange={(e) => setIsDownloadable(e.target.checked)}
                  disabled={updating}
                  className="w-4 h-4 rounded border-gray-300 text-gray-900 focus:ring-gray-900 cursor-pointer disabled:cursor-not-allowed"
                />
                <label className="text-xs font-semibold text-gray-700 cursor-pointer select-none" htmlFor="gallery-download">
                  Allow clients to download high-resolution photos
                </label>
              </div>

              <div className="flex justify-end pt-4 border-t border-gray-100">
                <button
                  type="submit"
                  disabled={updating || !title.trim() || (title.trim() === gallery.title && brandingColor === gallery.branding_color && isDownloadable === gallery.is_downloadable)}
                  className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {updating ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </form>
          </div>

          {/* Card 2: Security & Passwords */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2 border-b border-gray-100 pb-3">
              Password Protection
            </h2>
            <p className="text-xs text-gray-500 mb-6">
              When password protection is enabled, clients must authenticate before entering the public photo grid.
            </p>

            <form onSubmit={handleSavePassword} className="space-y-4">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-gray-700" htmlFor="gallery-password">
                  {hasPassword ? 'Update/Clear Password' : 'Set Protection Password'}
                </label>
                <div className="flex gap-3">
                  <input
                    id="gallery-password"
                    type="password"
                    placeholder={hasPassword ? '••••••••' : 'Enter security password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={updating}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-100 transition-all disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={updating}
                    className="px-4 py-2 border border-gray-200 text-gray-700 hover:text-gray-900 hover:bg-gray-50 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {password ? 'Save' : hasPassword ? 'Clear Protection' : 'Set Lock'}
                  </button>
                </div>
              </div>
            </form>
          </div>

          {/* Photo Management Section */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2 border-b border-gray-100 pb-3">
              Photo Management
            </h2>
            <p className="text-xs text-gray-500 mb-6">
              Upload multiple images to populate this collection. Once uploaded, clients can browse, view in lightbox, and download.
            </p>

            <DropZone onFiles={handleFilesSelected} disabled={updating} />

            {/* Symmetrical Component Linkage: Passes all multi-select and sorting handlers cleanly */}
            <PhotoGrid 
              photos={photos} 
              uploadQueue={uploadQueue} 
              onDeletePhotos={handleDeletePhotos}
              onReorderPhotos={handleReorderPhotos}
              onPhotoClick={setLightboxIndex} 
            />
          </div>
        </div>

        {/* RIGHT COLUMN: BRAND PREVIEW */}
        <div className="space-y-8">
          
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-6 flex flex-col items-center justify-center text-center py-10 min-h-[300px]">
            {gallery.cover_url ? (
              <img
                src={gallery.cover_url}
                alt={`${gallery.title} cover`}
                className="w-24 h-24 rounded-full object-cover border border-gray-100 mb-4 shadow-sm"
              />
            ) : (
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center text-white/30 mb-4"
                style={{ backgroundColor: brandingColor }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
              </div>
            )}
            <h3 className="text-sm font-semibold text-gray-900">{gallery.title}</h3>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border mt-2 ${
              gallery.is_published 
                ? 'bg-green-50 text-green-700 border-green-200' 
                : 'bg-yellow-50 text-yellow-700 border-yellow-200'
            }`}>
              {gallery.is_published ? 'Published' : 'Draft'}
            </span>
          </div>

        </div>
      </div>

      {/* Fullscreen Photo Lightbox Layer */}
      <PhotoLightbox
        photos={photos}
        currentIndex={lightboxIndex}
        onClose={() => setLightboxIndex(null)}
        onNavigate={setLightboxIndex}
      />
    </div>
  )
}

