import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGalleries } from '../../hooks/useGalleries'
import { galleriesApi } from '../../api/galleriesApi'
import Button from '../../components/ui/Button'
import Badge from '../../components/ui/Badge'
import Modal from '../../components/ui/Modal'
import Input from '../../components/ui/Input'
import { useToast } from '../../components/ui/Toast'
import { formatDate } from '../../utils/formatters'

/**
 * WHAT: Aligned and Optimized Galleries Dashboard Control Page
 * WHY: Clears code duplication by using custom hooks, aligns routes to slugs, and maps serializer fields [1.1.18, 1.2.2].
 * HOW: Imports useGalleries state manager [1.2.2] and binds elements strictly to schema properties [1.1.18].
 * WHERE: frontend/src/pages/dashboard/GalleriesPage.jsx
 */
export default function GalleriesPage() {
  const toast = useToast()
  
  // Consume your centralized state-management hook [1.2.2]
  const { galleries, setGalleries, loading, error } = useGalleries()

  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', branding_color: '#2C2825' })

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  // Auto-generate slug preview for visual UX helper on the form
  const generateSlugPreview = (title) => {
    return title
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.title.trim() || creating) return

    setCreating(true)
    try {
      // Dispatch payload to backend. The backend handles the unique slug calculation [1.1.18].
      const { data } = await galleriesApi.create({
        title: form.title.trim(),
        description: form.description.trim(),
        branding_color: form.branding_color,
      })

      toast('Gallery created!', 'success')
      setCreateOpen(false)
      setForm({ title: '', description: '', branding_color: '#2C2825' })

      // Optimistic UI state injection: Instantly prepend new item to list without refetching [1.2.2]
      setGalleries((prev) => [data, ...prev])
    } catch (err) {
      toast(err.response?.data?.error || 'Failed to create gallery.', 'error')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8 animate-fade-up">
        <div>
          <h1 className="font-serif text-4xl text-ink">Galleries</h1>
          <p className="text-sm text-muted mt-1">{galleries.length} galleries total</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/>
          </svg>
          New Gallery
        </Button>
      </div>

      {/* Render centralized network/database errors on page load [1.2.2] */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-100 text-red-600 rounded-2xl text-sm mb-6 animate-fade-up">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="skeleton h-52 rounded-2xl" />)}
        </div>
      ) : galleries.length === 0 ? (
        <div className="py-24 text-center border-2 border-dashed border-cream-300 rounded-2xl bg-cream-50 animate-fade-up">
          <p className="font-serif text-2xl text-ink mb-2">No galleries yet</p>
          <p className="text-muted text-sm mb-6">Create your first gallery to start delivering photos to clients.</p>
          <Button onClick={() => setCreateOpen(true)}>Create Gallery</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 animate-fade-up">
          {galleries.map((gallery, i) => (
            <Link
              key={gallery.id || gallery.slug}
              // STRICT REQUIREMENT: Dynamic routes must map to the slug identifier [1.1.18]
              to={`/dashboard/galleries/${gallery.slug}`}
              className="group bg-white rounded-2xl border border-cream-200 overflow-hidden hover:border-cream-400 hover:shadow-md transition-all duration-200"
              style={{ animationDelay: `${i * 0.05}s` }}
            >
              {/* Cover */}
              <div className="h-44 bg-cream-100 relative overflow-hidden">
                {/* CORRECT KEY: DRF list serializer returns flat 'cover_url' property [1.1.18] */}
                {gallery.cover_url ? (
                  <img
                    src={gallery.cover_url}
                    alt={gallery.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    loading="lazy"
                  />
                ) : (
                  <div
                    className="w-full h-full transition-all duration-300"
                    style={{ backgroundColor: gallery.branding_color + '15' }}
                  />
                )}
                <div
                  className="absolute bottom-0 left-0 right-0 h-1 transition-all duration-300"
                  style={{ backgroundColor: gallery.branding_color }}
                />
              </div>

              {/* Info */}
              <div className="p-4">
                <p className="font-medium text-ink truncate mb-2">{gallery.title}</p>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  <Badge variant={gallery.is_published ? 'success' : 'default'}>
                    {gallery.is_published ? 'Published' : 'Draft'}
                  </Badge>
                  {gallery.is_password_protected && <Badge variant="warning">🔒 Protected</Badge>}
                  {gallery.allow_download && <Badge variant="info">Downloads on</Badge>}
                </div>
                <p className="text-xs text-muted">Created {formatDate(gallery.created_at)}</p>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Create modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New Gallery">
        <form onSubmit={handleCreate} className="flex flex-col gap-4">
          <Input
            label="Gallery title"
            placeholder="Wedding — Jane & John"
            value={form.title}
            onChange={set('title')}
            required
            disabled={creating}
          />
          <div>
            <label className="text-sm font-medium text-ink/80 block mb-1">Description</label>
            <textarea
              className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm text-ink placeholder:text-muted focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200 resize-none disabled:bg-cream-50"
              rows={3}
              placeholder="Optional description for this gallery..."
              value={form.description}
              onChange={set('description')}
              disabled={creating}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-ink/80 block mb-1">Branding color</label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={form.branding_color}
                onChange={set('branding_color')}
                className="w-10 h-10 rounded-lg border border-cream-300 cursor-pointer disabled:opacity-50"
                disabled={creating}
              />
              <span className="text-sm text-muted font-mono">{form.branding_color}</span>
            </div>
          </div>

          {form.title.trim() && (
            <div className="p-4 bg-cream-50 rounded-2xl border border-cream-100">
              <span className="text-[10px] font-bold text-muted/80 tracking-wider uppercase">
                Dynamic Link Preview
              </span>
              <p className="text-xs font-semibold text-ink/80 mt-1 truncate">
                yourname.kyapture.com/gallery/
                <span className="text-brand-primary font-bold font-mono">
                  {generateSlugPreview(form.title)}
                </span>
              </p>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)} className="flex-1" disabled={creating}>
              Cancel
            </Button>
            <Button type="submit" loading={creating} className="flex-1" disabled={!form.title.trim()}>
              Create Gallery
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}