import { useState, useEffect, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { galleriesApi } from '../../api/galleriesApi'
import { mockGalleries } from '../../utils/mockGalleries'
import Spinner from '../../components/ui/Spinner'
import DropZone from '../../components/ui/DropZone'
import PhotoGrid from '../../components/shared/PhotoGrid'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

/**
 * WHAT: Gallery Detail Management Page
 * WHY:  Centralizes individual gallery settings, password controls, download access,
 *       and provides a fully interactive offline-safe photo upload simulator [14].
 */
export default function GalleryDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [gallery, setGallery]       = useState(null)
  const [loading, setLoading]       = useState(true)
  const [errorMsg, setErrorMsg]     = useState('')
  const [updating, setUpdating]     = useState(false)   // Bug 1 Fix: setSubmitting → setUpdating
  const [copied, setCopied]         = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)   // Bug 7 Fix: surface clipboard errors

  // ── PHOTO-MANAGEMENT STATES ──────────────────────────────────────────────
  const [photos, setPhotos]           = useState([])
  const [uploadQueue, setUploadQueue] = useState([])

  // Local Form States
  const [title, setTitle]               = useState('')
  const [brandingColor, setBrandingColor] = useState('#000000')
  const [isDownloadable, setIsDownloadable] = useState(false)
  const [password, setPassword]         = useState('')
  const [hasPassword, setHasPassword]   = useState(false)

  const isMountedRef      = useRef(false)
  const copyTimeoutRef    = useRef(null)
  const skipNextLoadRef   = useRef(false)   // Bug 4 Fix: skip redundant reload after slug-change navigate

  // ── NEW BUG A FIX: Track every interval spawned by the upload simulator ──
  // The merged code created intervals inside handleFilesSelected but never stored
  // them anywhere. On unmount, all in-progress intervals kept firing forever,
  // calling setState on a dead component (wasting CPU + leaking closures).
  const uploadIntervalsRef = useRef([])

  // ── NEW BUG A+C FIX: Track every blob URL we create ──────────────────────
  // Every URL.createObjectURL() call allocates browser memory that must be
  // explicitly released with URL.revokeObjectURL(). We centralise the registry
  // here so the unmount cleanup can free them all in one sweep regardless of
  // which state array (uploadQueue vs photos) the URL ended up in.
  const blobUrlsRef = useRef([])

  // ── MOUNT / UNMOUNT LIFECYCLE ─────────────────────────────────────────────
  // NEW BUG A FIX (critical): The merged code wrote this effect with [uploadQueue]
  // as its dependency. That caused the cleanup function — which calls
  // URL.revokeObjectURL for every item in the queue — to fire on EVERY progress
  // update (every 300 ms). In practice this revoked the blob URL of every
  // in-progress upload within 300 ms of it starting, permanently breaking all
  // upload previews and the completed photo grid.
  //
  // The fix is simple but non-obvious: use an EMPTY dependency array [] so the
  // effect runs only on true mount/unmount, never mid-session. Blob URL cleanup
  // is handled via blobUrlsRef instead (see above), which always holds the full
  // lifetime registry regardless of which state array items currently live in.
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)

      // Kill all in-progress upload intervals (Bug A Fix)
      uploadIntervalsRef.current.forEach(clearInterval)

      // Revoke every blob URL created during this page session (Bug C Fix)
      blobUrlsRef.current.forEach(url => URL.revokeObjectURL(url))
    }
  }, []) // ← EMPTY — intentional. See note above.

  // ── Bug 3 Fix: Centralized form state synchronization helper ─────────────
  const syncFormFromGallery = (data) => {
    setGallery(data)
    setTitle(data.title)
    setBrandingColor(data.branding_color)
    setIsDownloadable(data.is_downloadable)
    setHasPassword(data.has_password)
  }

  // ── DATA LOADING LIFE-CYCLE ───────────────────────────────────────────────
  useEffect(() => {
    async function loadGallery() {
      // Bug 4 Fix: Skip reload when useParams id shifted but data is already hydrated
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
          if (!match) {
            if (isMountedRef.current) {
              setErrorMsg('Collection not found.')
              setLoading(false)
            }
            return
          }
          if (isMountedRef.current) {
            syncFormFromGallery(match)
            setPhotos(match.slug === 'mila-portraits' ? [
              { id: 'mock-img-1', image_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80' },
              { id: 'mock-img-2', image_url: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=400&q=80' },
            ] : [])
            setLoading(false)
          }
        }, 300)
        return
      }

      try {
        const data = await galleriesApi.getGallery(id)
        if (isMountedRef.current) {
          syncFormFromGallery(data)
          setPhotos(data.photos || [])
        }
      } catch (err) {
        if (isMountedRef.current) {
          setErrorMsg(err.response?.data?.detail || 'Failed to retrieve collection configurations.')
        }
      } finally {
        // Bug 5 Fix: !USE_MOCK_DATA guard removed — always true here since mock path returns early
        if (isMountedRef.current) {
          setLoading(false)
        }
      }
    }

    loadGallery()
  }, [id])

  // ── PHOTO UPLOAD SIMULATOR ────────────────────────────────────────────────
  const handleFilesSelected = (files) => {
    const queueItems = files.map(file => {
      const previewUrl = URL.createObjectURL(file)

      // NEW BUG A+C FIX: Register every blob URL at creation time.
      // This means the unmount cleanup in useEffect([]) can always free them,
      // regardless of whether the item is still in uploadQueue, already moved to
      // photos, or somewhere in between when the component tears down.
      blobUrlsRef.current.push(previewUrl)

      return {
        id: Math.random().toString(36).substring(2, 9),
        file,
        previewUrl,
        progress: 0,
      }
    })

    setUploadQueue(prev => [...prev, ...queueItems])

    queueItems.forEach(item => {
      let currentProgress = 0

      const interval = setInterval(() => {
        currentProgress += Math.floor(Math.random() * 15) + 5

        if (currentProgress >= 100) {
          currentProgress = 100
          clearInterval(interval)

          // NEW BUG A FIX: Remove the completed interval from the registry so
          // the unmount cleanup doesn't try to clear an already-cleared handle.
          uploadIntervalsRef.current = uploadIntervalsRef.current.filter(i => i !== interval)

          if (isMountedRef.current) {
            setPhotos(prev => [...prev, { id: item.id, image_url: item.previewUrl }])
            setUploadQueue(prev => prev.filter(q => q.id !== item.id))
          }
        } else {
          if (isMountedRef.current) {
            setUploadQueue(prev =>
              prev.map(q => q.id === item.id ? { ...q, progress: currentProgress } : q)
            )
          }
        }
      }, 300)

      // NEW BUG A FIX: Store the interval ID so unmount can clear it
      uploadIntervalsRef.current.push(interval)
    })
  }

  const handleDeletePhoto = (photoId) => {
    setPhotos(prev => {
      const photo = prev.find(p => p.id === photoId)

      // NEW BUG C FIX: When a locally-uploaded photo (blob: URL) is deleted,
      // the original code left its object URL allocated forever. Revoke it here.
      // We also remove it from blobUrlsRef so the unmount sweep doesn't attempt
      // a double-revoke (which is a silent no-op but confusing during debugging).
      if (photo?.image_url?.startsWith('blob:')) {
        URL.revokeObjectURL(photo.image_url)
        blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== photo.image_url)
      }

      return prev.filter(p => p.id !== photoId)
    })

    // NOTE FOR REAL-API MODE: add a galleriesApi.deletePhoto(id, photoId) call
    // here. Without it, the photo will reappear on next page load because the
    // current deletion is purely optimistic/local. The mock simulator is fine
    // as-is since there is no remote state to sync.
  }

  // ── SETTINGS OPERATIONS ───────────────────────────────────────────────────

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
        // Bug 6 Fix: Simulate backend slug recalculation so navigate fires in mock mode
        const mockSlug = payload.title
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-+|-+$/g, '')
        updated = { ...gallery, ...payload, slug: mockSlug }
      } else {
        updated = await galleriesApi.updateGallery(id, payload)
      }

      // Bug 3 Fix: Sync all form states to saved values so Save button disabled
      // condition stays accurate after the server trims/transforms the title
      syncFormFromGallery(updated)

      if (updated.slug !== id) {
        // Bug 4 Fix: Flag the upcoming useEffect([id]) run to skip the redundant refetch
        skipNextLoadRef.current = true
        navigate(`/dashboard/galleries/${updated.slug}`, { replace: true })
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to save collection configurations.')
      }
    } finally {
      if (isMountedRef.current) setUpdating(false)
    }
  }

  const handleTogglePublish = async () => {
    if (updating || !gallery) return
    setUpdating(true)
    setErrorMsg('')

    const nextState = !gallery.is_published

    try {
      if (USE_MOCK_DATA) {
        setGallery(prev => ({ ...prev, is_published: nextState }))
      } else {
        await galleriesApi.publishGallery(id, nextState)
        setGallery(prev => ({ ...prev, is_published: nextState }))
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to update publication status.')
      }
    } finally {
      if (isMountedRef.current) setUpdating(false)
    }
  }

  const handleSavePassword = async (e) => {
    e.preventDefault()
    if (updating) return

    // Bug 8 Fix: Confirm before removing password protection
    if (!password && hasPassword) {
      const confirmed = window.confirm(
        'Remove password protection from this gallery? Clients will no longer need to authenticate.'
      )
      if (!confirmed) return
    }

    setUpdating(true)
    setErrorMsg('')

    try {
      if (USE_MOCK_DATA) {
        const newHasPassword = Boolean(password)
        setHasPassword(newHasPassword)
        setGallery(prev => ({ ...prev, has_password: newHasPassword }))
        setPassword('')
      } else {
        const response = await galleriesApi.setGalleryPassword(id, password || null)
        setHasPassword(response.has_password)
        setGallery(prev => ({ ...prev, has_password: response.has_password }))
        setPassword('')
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Failed to update security credentials.')
      }
    } finally {
      if (isMountedRef.current) setUpdating(false)
    }
  }

  const handleCopyLink = async () => {
    if (!gallery) return

    // Bug 2 Fix: Dynamic username from API data, not hardcoded 'kroman'
    const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'
    const clientURL = `${window.location.protocol}//${window.location.host}/g/${ownerUsername}/${gallery.slug}`

    try {
      await navigator.clipboard.writeText(clientURL)
      setCopied(true)
      setCopyFailed(false)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy link:', err)
      // Bug 7 Fix: Show failure state in the button — not just console
      setCopyFailed(true)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopyFailed(false), 2000)
    }
  }

  // ── RENDERS ───────────────────────────────────────────────────────────────

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

  // Bug 2 Fix: Single source of truth for owner username — used in slug preview + copy link
  const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeUp">

      {/* ── HEADER NAVIGATION ── */}
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

      {/* ── CENTRALIZED SETTINGS GRID ── */}
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

              {/* Slug Preview — Bug 2 Fix: dynamic ownerUsername */}
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-100 text-xs">
                <span className="font-semibold text-gray-400 uppercase tracking-wider block text-[10px]">
                  Live Slug Link
                </span>
                <p className="mt-1 font-semibold text-gray-600 truncate">
                  yourname.kyapture.com/g/{ownerUsername}/
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
                    className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer overflow-hidden p-0 bg-transparent disabled:cursor-not-allowed"
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
                  disabled={
                    updating ||
                    !title.trim() ||
                    // Bug 3 Fix: compare trimmed value to avoid whitespace false-positives
                    (
                      title.trim() === gallery.title &&
                      brandingColor === gallery.branding_color &&
                      isDownloadable === gallery.is_downloadable
                    )
                  }
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

          {/* Card 3: Photo Management */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2 border-b border-gray-100 pb-3">
              Photo Management
            </h2>
            <p className="text-xs text-gray-500 mb-6">
              Upload multiple images to populate this collection. Once uploaded, clients can browse, view in lightbox, and download.
            </p>

            <DropZone onFilesSelected={handleFilesSelected} disabled={updating} />

            <PhotoGrid
              photos={photos}
              uploadQueue={uploadQueue}
              onDeletePhoto={handleDeletePhoto}
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
    </div>
  )
}