// File Location: frontend/src/pages/dashboard/GalleriesPage.jsx
// VERSION: Production-Grade Galleries View — Week 10
// Corrects API naming mismatches, resolves slug parameters, and handles 403 gating messages.

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { galleriesApi }        from '../../api/galleriesApi'
import { useAuthStore }        from '../../store/authStore'
import { useToast }            from '../../components/ui/Toast'
import { getAlphaBrandingColor } from '../../utils/colorHelper'
import Modal   from '../../components/ui/Modal'
import Spinner from '../../components/ui/Spinner'

export default function GalleriesPage() {
  const toast    = useToast()
  const navigate = useNavigate()

  // BUG RESOLUTION: Retrieve photographer username from session store, not useSubdomain()
  const username = useAuthStore((s) => s.user?.username)

  // Layout & UI States
  const [galleries,  setGalleries]  = useState([])
  const [loading,    setLoading]    = useState(true)
  const [openCreate, setOpenCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const [formData, setFormData] = useState({
    title: '',
    branding_color: '#4a7c6f', // Kyapture brand primary green
  })

  // ── 1. Fetch galleries on mount ────────────────────────────────────────────
  useEffect(() => {
    galleriesApi.getGalleries()
      .then((data) => {
        // Defensive analysis: Safe check for paginated objects vs flat arrays
        const list = data?.results || (Array.isArray(data) ? data : [])
        setGalleries(list)
      })
      .catch(() => toast('Failed to load collections.', 'error'))
      .finally(() => setLoading(false))
  }, [toast])

  // ── 2. Create collection ───────────────────────────────────────────────────
  const handleCreateSubmit = async (e) => {
    e.preventDefault()

    if (!formData.title.trim()) {
      toast('Please enter a collection title.', 'warning')
      return
    }

    setSubmitting(true)
    const loaderId = toast('Creating your new collection…', 'loading')

    try {
      const newGallery = await galleriesApi.createGallery({
        title:          formData.title.trim(),
        branding_color: formData.branding_color,
      })

      toast.dismiss(loaderId)
      toast('Collection created!', 'success')

      setGalleries((prev) => [newGallery, ...prev])
      setOpenCreate(false)
      setFormData({ title: '', branding_color: '#4a7c6f' })
    } catch (err) {
      toast.dismiss(loaderId)

      // ── SUBSCRIPTION PLAN GATING (403 FORBIDDEN INTERCEPTOR) ────────────────
      // Resolves AI Studio bug by prioritizing custom limit error payloads
      // (such as "You have used 3 of 3 galleries on the Free plan") over static strings.
      if (err.response?.status === 403) {
        const data = err.response?.data
        const message = data?.message || data?.detail || 'Upgrade your plan to create more galleries.'

        toast(message, 'warning')
        setOpenCreate(false)
        
        setTimeout(() => navigate('/dashboard/billing'), 2200)
      } else {
        const errorMsg = err.response?.data?.error || err.response?.data?.detail || 'Failed to create collection.'
        toast(errorMsg, 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── 3. Copy public gallery link ────────────────────────────────────────────
  // Compiles standard, path-based fallback links to match routing configurations.
  const handleCopyLink = async (gallery) => {
    if (!username) {
      toast('Unable to build link — profile not loaded yet.', 'error')
      return
    }
    
    const link = `${window.location.origin}/g/${username}/${gallery.slug}`
    
    try {
      await navigator.clipboard.writeText(link)
      toast('Gallery link copied!', 'success')
    } catch {
      toast('Could not copy link. Copy it manually from the address bar.', 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex h-[60vh] w-full items-center justify-center">
        <Spinner size="lg" className="text-ink" />
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8" style={{ animation: 'fadeUp 0.5s ease both' }}>
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="font-serif text-4xl text-ink">My Collections</h1>
          <p className="text-xs text-muted">Create, manage, and deliver photo collections to your clients [weekly tasks.txt].</p>
        </div>
        <button
          type="button"
          onClick={() => setOpenCreate(true)}
          className="sm:self-start px-5 py-3 bg-ink hover:opacity-90 active:scale-[0.98] transition-all text-white text-xs uppercase tracking-widest rounded-lg font-medium cursor-pointer"
        >
          Create Gallery
        </button>
      </header>

      {/* Empty state */}
      {galleries.length === 0 ? (
        <div className="text-center py-24 border-2 border-dashed border-cream-300 rounded-2xl bg-cream-50/50 space-y-4">
          <svg className="w-10 h-10 text-muted mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
          </svg>
          <p className="text-sm text-muted font-light">No collections yet. Create your first gallery to begin.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {galleries.map((gallery) => {
            const highlightBg = getAlphaBrandingColor(gallery.branding_color, '14')

            return (
              <div
                key={gallery.id}
                className="group bg-white border border-cream-200 rounded-2xl overflow-hidden hover:shadow-md hover:border-cream-300 transition-all duration-300 flex flex-col h-full"
              >
                {/* Cover area */}
                <div className="h-44 bg-cream-100 overflow-hidden relative flex-shrink-0">
                  {gallery.cover_url ? (
                    <img
                      src={gallery.cover_url}
                      alt=""
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                    />
                  ) : (
                    <div className="w-full h-full" style={{ backgroundColor: highlightBg }} />
                  )}

                  <div
                    className="absolute bottom-0 left-0 right-0 h-1"
                    style={{ backgroundColor: gallery.branding_color }}
                  />

                  {gallery.has_password && (
                    <div className="absolute top-3 right-3 bg-white/90 rounded-lg p-1.5 shadow-sm">
                      <svg className="w-4 h-4 text-ink" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                      </svg>
                    </div>
                  )}
                </div>

                {/* Card body */}
                <div className="p-5 flex flex-col flex-1 justify-between gap-4">
                  <div className="space-y-1">
                    <h3 className="font-serif text-lg font-bold text-ink group-hover:text-stone-700 transition-colors line-clamp-1">
                      {gallery.title}
                    </h3>
                    <p className="text-[10px] text-muted uppercase tracking-wider">
                      {gallery.photo_count || 0} image{gallery.photo_count !== 1 ? 's' : ''}
                    </p>
                  </div>

                  <div className="flex gap-2">
                    {/* BUG RESOLUTION: Navigate via gallery.slug instead of UUID id */}
                    <button
                      type="button"
                      onClick={() => navigate(`/dashboard/galleries/${gallery.slug}`)}
                      className="flex-1 py-2.5 border border-cream-300 hover:border-cream-400 text-ink text-xs uppercase tracking-widest rounded-lg font-medium transition-colors cursor-pointer bg-white"
                    >
                      Manage
                    </button>
                    <button
                      type="button"
                      onClick={() => handleCopyLink(gallery)}
                      title="Copy public gallery link"
                      aria-label="Copy public gallery link"
                      className="px-3 py-2.5 border border-cream-300 hover:border-cream-400 text-muted hover:text-ink rounded-lg transition-colors cursor-pointer bg-white"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Create Gallery Modal Overlay */}
      <Modal
        open={openCreate}
        onClose={() => setOpenCreate(false)}
        title="Create Collection"
        size="sm"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          <div>
            <label htmlFor="gallery-title" className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">
              Collection Title
            </label>
            <input
              id="gallery-title"
              type="text"
              value={formData.title}
              onChange={(e) => setFormData((f) => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Wedding of Sonal & Lalit"
              disabled={submitting}
              maxLength={60}
              className="w-full border border-cream-300 p-3 rounded-lg text-xs text-ink focus:border-ink focus:ring-0 outline-none bg-white"
            />
          </div>

          <div>
            <label htmlFor="gallery-color" className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">
              Primary Accent Color
            </label>
            <div className="flex items-center gap-3">
              <input
                id="gallery-color"
                type="color"
                value={formData.branding_color}
                onChange={(e) => setFormData((f) => ({ ...f, branding_color: e.target.value }))}
                disabled={submitting}
                className="w-10 h-10 border-0 rounded cursor-pointer"
              />
              <span className="text-xs font-mono text-muted uppercase">{formData.branding_color}</span>
            </div>
          </div>

          <div className="flex gap-3 pt-4 border-t border-cream-100">
            <button
              type="button"
              onClick={() => setOpenCreate(false)}
              disabled={submitting}
              className="w-1/2 py-3 border border-cream-300 hover:bg-cream-50 text-ink text-xs uppercase tracking-widest rounded-lg font-medium cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="w-1/2 py-3 bg-ink hover:opacity-90 text-white text-xs uppercase tracking-widest rounded-lg font-medium cursor-pointer disabled:opacity-50"
            >
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}