// frontend/src/pages/client/ClientGalleryPage.jsx

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClientStore } from '../../store/clientStore'
import { clientsApi } from '../../api/clientsApi'
import { getAlphaBrandingColor } from '../../utils/colorHelper'
import ClientLayout from '../../components/layout/ClientLayout'
import PublicMasonryGrid from '../../components/shared/PublicMasonryGrid'
import PhotoLightbox from '../../components/shared/PhotoLightbox'
import PasswordModal from '../../components/shared/PasswordModal'
import Spinner from '../../components/ui/Spinner'

export default function ClientGalleryPage() {
  // BUG FIX: username was being read from useSubdomain(), which parses
  // window.location.hostname — but the actual route is /g/:username/:slug,
  // a PATH parameter (confirmed in App.jsx). useSubdomain() has nothing to
  // do with this page: on localhost it returns null (fewer than 3 hostname
  // segments), and even in production on app.kyapture.com it would return
  // 'app' — the SPA's own subdomain, never the photographer's username from
  // the URL. Since fetchGallery's `if (!username) return` guard fires
  // before setLoading is ever called, this left the page stuck on an
  // infinite loading spinner in dev, for every gallery, always.
  const { username, slug } = useParams()

  const sessionKey = `${username}:${slug}`
  const { sessions, setSession, hasHydrated } = useClientStore()
  const token = sessions[sessionKey] ?? null

  const [galleryTitle,     setGalleryTitle]     = useState('')
  const [photographerName, setPhotographerName] = useState('')
  const [photographerLogo, setPhotographerLogo] = useState(null)
  const [brandingColor,    setBrandingColor]    = useState(null)
  const [photos,           setPhotos]           = useState([])
  const [allowDownload,    setAllowDownload]    = useState(false)

  const [loading,   setLoading]   = useState(true)
  const [notFound,  setNotFound]  = useState(false)
  const [error,     setError]     = useState(false)
  const [locked,    setLocked]    = useState(false)
  const [pwLoading, setPwLoading] = useState(false)
  const [pwError,   setPwError]   = useState(null)

  const [lightboxIndex, setLightboxIndex] = useState(null)

  const activeFetchId      = useRef(0)
  const activeUnlockId     = useRef(0)
  const abortControllerRef = useRef(null)

  const applyGalleryData = useCallback((data) => {
    setGalleryTitle(data.title || '')
    setPhotographerName(data.photographer_name || '')
    setPhotographerLogo(data.photographer_logo || null)
    setPhotos(data.photos || [])
    setLocked(false)
    setAllowDownload(data.allow_download || false)

    if (data.branding_color) {
      setBrandingColor(data.branding_color)
      document.documentElement.style.setProperty('--brand-color', data.branding_color)
    }
  }, [])

  const fetchGallery = useCallback(async (currentToken, fetchId) => {
    if (!username) return

    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setNotFound(false)
    setError(false)
    setPwError(null)

    try {
      // clientsApi.getGallery now correctly forwards { signal } to Axios —
      // previously this component built the AbortController but the
      // signal never reached the actual HTTP request, since getGallery's
      // signature only accepted (username, slug, token) with nowhere to
      // put the config.
      const { data } = await clientsApi.getGallery(username, slug, currentToken, {
        signal: controller.signal,
      })

      if (fetchId !== activeFetchId.current) return

      if (data.requires_password) {
        setGalleryTitle(data.title || '')
        setPhotographerName(data.photographer_name || '')
        if (data.branding_color) {
          setBrandingColor(data.branding_color)
          document.documentElement.style.setProperty('--brand-color', data.branding_color)
        }
        if (currentToken) setSession(sessionKey, null)
        setLocked(true)
        setPhotos([])
        return
      }

      applyGalleryData(data)
    } catch (err) {
      if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return
      if (fetchId !== activeFetchId.current) return

      const status = err.response?.status
      if (status === 404) {
        setNotFound(true)
        return
      }
      if (status === 401) {
        setSession(sessionKey, null)
        setLocked(true)
        setPhotos([])
        return
      }
      setError(true)
    } finally {
      if (fetchId === activeFetchId.current) setLoading(false)
    }
  }, [username, slug, sessionKey, applyGalleryData, setSession])

  useEffect(() => {
    if (!hasHydrated || !username) return

    const currentFetchId = ++activeFetchId.current
    fetchGallery(token, currentFetchId)

    return () => {
      abortControllerRef.current?.abort()
      document.documentElement.style.removeProperty('--brand-color')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, slug, hasHydrated])

  const handleUnlock = async (password) => {
    if (!username) return

    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    const unlockId = ++activeUnlockId.current

    setPwLoading(true)
    setPwError(null)
    try {
      const { data } = await clientsApi.unlock(username, slug, password, {
        signal: controller.signal,
      })
      setSession(sessionKey, data.access_token)

      const currentFetchId = ++activeFetchId.current
      await fetchGallery(data.access_token, currentFetchId)
    } catch (err) {
      if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return
      if (unlockId !== activeUnlockId.current) return
      const msg = err.response?.data?.password?.[0]
        || err.response?.data?.detail
        || 'Incorrect password. Please try again.'
      setPwError(msg)
    } finally {
      if (unlockId === activeUnlockId.current) setPwLoading(false)
    }
  }

  const retry = () => {
    const currentFetchId = ++activeFetchId.current
    fetchGallery(token, currentFetchId)
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-cream-50">
        <Spinner className="w-8 h-8 text-ink" />
        <p className="mt-4 text-xs tracking-widest text-muted uppercase font-light">
          Loading collection…
        </p>
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-cream-50 px-6 text-center">
        <h1 className="font-serif text-2xl text-ink mb-2">Gallery not found</h1>
        <p className="text-sm text-muted max-w-xs">
          This gallery doesn't exist or is no longer available.
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-cream-50 px-6 text-center">
        <h1 className="font-serif text-2xl text-ink mb-2">Something went wrong</h1>
        <p className="text-sm text-muted max-w-xs mb-6">
          We couldn't load this gallery. Please try again.
        </p>
        <button
          type="button"
          onClick={retry}
          className="text-xs uppercase tracking-widest text-ink border border-ink/30 px-4 py-2 rounded-full hover:bg-ink/5 transition"
        >
          Retry
        </button>
      </div>
    )
  }

  if (locked) {
    const backgroundGradientColor = getAlphaBrandingColor(brandingColor, '14')
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center px-6"
        style={{
          background: `linear-gradient(180deg, ${backgroundGradientColor} 0%, #fdfbf7 100%)`,
        }}
      >
        {galleryTitle && (
          <h1 className="font-serif text-3xl text-ink mb-1 text-center">{galleryTitle}</h1>
        )}
        {photographerName && (
          <p className="text-xs uppercase tracking-[0.2em] text-muted mb-8">
            By {photographerName}
          </p>
        )}
        <PasswordModal
          open={locked}
          onSubmit={handleUnlock}
          error={pwError}
          loading={pwLoading}
        />
      </div>
    )
  }

  return (
    <ClientLayout photographer={{ display_name: photographerName }}>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 animate-fadeUp">
        <header className="text-center mb-16">
          {photographerLogo && (
            <img
              src={photographerLogo}
              alt={photographerName}
              className="h-14 mx-auto mb-6 object-contain"
            />
          )}
          <h1 className="text-4xl sm:text-5xl font-serif font-medium text-ink tracking-tight">
            {galleryTitle}
          </h1>
          <div
            className="h-px w-12 mx-auto my-6"
            style={{ backgroundColor: brandingColor || 'var(--accent)' }}
          />
          {photographerName && (
            <p className="text-xs uppercase tracking-[0.2em] text-muted font-light">
              By {photographerName}
            </p>
          )}
        </header>

        {photos.length > 0 && (
          <p className="text-xs text-muted text-center mb-4">
            {photos.length} photo{photos.length !== 1 ? 's' : ''}
          </p>
        )}

        {allowDownload && photos.length > 0 && (
          <div className="text-center mb-8">
            <Link
              to={`/g/${username}/${slug}/download`}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-ink text-[#fdfbf7] text-xs uppercase tracking-widest font-semibold rounded-full hover:opacity-90 transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-ink focus:ring-offset-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download All Photos
            </Link>
          </div>
        )}

        {photos.length === 0 ? (
          <div className="text-center py-24 border border-dashed border-cream-200 rounded-xl bg-cream-50">
            <p className="text-sm text-muted font-light">No images in this collection yet.</p>
          </div>
        ) : (
          <PublicMasonryGrid photos={photos} onPhotoClick={setLightboxIndex} />
        )}

        {lightboxIndex !== null && (
          <PhotoLightbox
            photos={photos}
            index={lightboxIndex}
            onClose={() => setLightboxIndex(null)}
            onChange={setLightboxIndex}
          />
        )}
      </main>
    </ClientLayout>
  )
}