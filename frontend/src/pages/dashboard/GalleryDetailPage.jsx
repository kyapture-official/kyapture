import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { galleriesApi } from '../../api/galleriesApi'
import { photosApi } from '../../api/photosApi'
import Button from '../../components/ui/Button'
import Badge from '../../components/ui/Badge'
import PhotoGrid from '../../components/shared/PhotoGrid'
import DropZone from '../../components/ui/DropZone'
import { useToast } from '../../components/ui/Toast'
import { useAuthStore } from '../../store/authStore'

export default function GalleryDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuthStore()

  const [gallery, setGallery] = useState(null)
  const [photos, setPhotos] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadQueue, setUploadQueue] = useState([])
  const [tab, setTab] = useState('photos')

  const loadGallery = () =>
    Promise.all([
      galleriesApi.get(id).then((r) => setGallery(r.data)),
      photosApi.list(id).then((r) => setPhotos(r.data.results || r.data)),
    ]).finally(() => setLoading(false))

  useEffect(() => { loadGallery() }, [id])

  const handleFiles = async (files) => {
    setUploading(true)
    setUploadQueue(files.map((f) => ({ name: f.name, progress: 0 })))
    for (let i = 0; i < files.length; i++) {
      const fd = new FormData()
      fd.append('image', files[i])
      fd.append('gallery', id)
      fd.append('original_name', files[i].name)
      fd.append('file_size', files[i].size)
      try {
        const { data } = await photosApi.upload(id, fd)
        setPhotos((p) => [...p, data])
        setUploadQueue((q) => q.map((x, j) => j === i ? { ...x, progress: 100 } : x))
      } catch {
        toast(`Failed to upload ${files[i].name}`, 'error')
      }
    }
    setUploading(false)
    setUploadQueue([])
    toast('Upload complete!', 'success')
  }

  const handleDelete = async (photoId) => {
    if (!confirm('Delete this photo?')) return
    try {
      await photosApi.delete(photoId)
      setPhotos((p) => p.filter((x) => x.id !== photoId))
      toast('Photo deleted.', 'success')
    } catch {
      toast('Failed to delete photo.', 'error')
    }
  }

  const togglePublish = async () => {
    try {
      if (gallery.is_published) {
        await galleriesApi.unpublish(id)
        setGallery((g) => ({ ...g, is_published: false }))
        toast('Gallery unpublished.', 'info')
      } else {
        await galleriesApi.publish(id)
        setGallery((g) => ({ ...g, is_published: true }))
        toast('Gallery is now live!', 'success')
      }
    } catch {
      toast('Action failed.', 'error')
    }
  }

  const handleDelete_gallery = async () => {
    if (!confirm('Delete this entire gallery? This cannot be undone.')) return
    await galleriesApi.delete(id)
    navigate('/dashboard/galleries')
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-10 w-64 rounded-xl" />
        <div className="skeleton h-6 w-40 rounded-xl" />
        <div className="grid grid-cols-3 gap-3 mt-8">
          {[1,2,3,4,5,6].map(i => <div key={i} className="skeleton rounded-xl aspect-square" />)}
        </div>
      </div>
    )
  }

  if (!gallery) return <div className="text-muted">Gallery not found.</div>

  const clientUrl = `${window.location.protocol}//${user?.username}.kyapture.com/${gallery.slug}`

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-8 animate-fade-up">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button onClick={() => navigate('/dashboard/galleries')} className="text-muted hover:text-ink">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7"/>
              </svg>
            </button>
            <h1 className="font-serif text-3xl text-ink">{gallery.title}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={gallery.is_published ? 'success' : 'default'}>
              {gallery.is_published ? 'Published' : 'Draft'}
            </Badge>
            {gallery.is_password_protected && <Badge variant="warning">Protected</Badge>}
            <span className="text-xs text-muted">{photos.length} photos</span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {gallery.is_published && (
            <a
              href={clientUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted border border-cream-300 px-3 py-1.5 rounded-lg hover:border-cream-400 transition-colors"
            >
              View live ↗
            </a>
          )}
          <Button
            variant={gallery.is_published ? 'secondary' : 'primary'}
            size="sm"
            onClick={togglePublish}
          >
            {gallery.is_published ? 'Unpublish' : 'Publish'}
          </Button>
          <Button variant="danger" size="sm" onClick={handleDelete_gallery}>Delete</Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-cream-100 rounded-xl p-1 mb-6 w-fit animate-fade-up delay-100">
        {['photos', 'upload', 'settings'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 capitalize
              ${tab === t ? 'bg-white text-ink shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="animate-fade-in">
        {tab === 'photos' && (
          <PhotoGrid photos={photos} onDelete={handleDelete} showActions />
        )}

        {tab === 'upload' && (
          <div className="max-w-xl">
            <DropZone onFiles={handleFiles} multiple />
            {uploadQueue.length > 0 && (
              <div className="mt-4 space-y-2">
                {uploadQueue.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 bg-white rounded-xl border border-cream-200 px-4 py-3">
                    <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/>
                    </svg>
                    <span className="flex-1 text-sm text-ink truncate">{f.name}</span>
                    <span className="text-xs text-muted">{f.progress === 100 ? '✓' : 'uploading…'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'settings' && (
          <GallerySettings gallery={gallery} id={id} onUpdate={setGallery} />
        )}
      </div>
    </div>
  )
}

function GallerySettings({ gallery, id, onUpdate }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: gallery.title,
    description: gallery.description || '',
    branding_color: gallery.branding_color,
    allow_download: gallery.allow_download,
    watermark_enabled: gallery.watermark_enabled,
    is_password_protected: gallery.is_password_protected,
    password: '',
  })
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const toggle = (k) => () => setForm((f) => ({ ...f, [k]: !f[k] }))

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const { data } = await galleriesApi.update(id, form)
      onUpdate(data)
      toast('Settings saved!', 'success')
    } catch {
      toast('Failed to save.', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="max-w-lg flex flex-col gap-5">
      <div>
        <label className="text-sm font-medium text-ink/80 block mb-1">Title</label>
        <input
          className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm text-ink focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200"
          value={form.title}
          onChange={set('title')}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-ink/80 block mb-1">Description</label>
        <textarea
          className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm text-ink focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200 resize-none"
          rows={3}
          value={form.description}
          onChange={set('description')}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-ink/80 block mb-1">Branding Color</label>
        <div className="flex items-center gap-3">
          <input type="color" value={form.branding_color} onChange={set('branding_color')}
            className="w-10 h-10 rounded-lg border border-cream-300 cursor-pointer" />
          <span className="text-sm text-muted">{form.branding_color}</span>
        </div>
      </div>

      {/* Toggles */}
      <div className="flex flex-col gap-3">
        {[
          { key: 'allow_download', label: 'Allow photo downloads', desc: 'Clients can download original photos' },
          { key: 'watermark_enabled', label: 'Watermark photos', desc: 'Apply watermark to all displayed photos' },
          { key: 'is_password_protected', label: 'Password protect', desc: 'Require a password to view this gallery' },
        ].map(({ key, label, desc }) => (
          <label key={key} className="flex items-center justify-between cursor-pointer bg-white border border-cream-200 rounded-xl px-4 py-3">
            <div>
              <p className="text-sm font-medium text-ink">{label}</p>
              <p className="text-xs text-muted">{desc}</p>
            </div>
            <div
              onClick={toggle(key)}
              className={`w-11 h-6 rounded-full transition-colors duration-200 relative flex items-center
                ${form[key] ? 'bg-ink' : 'bg-cream-300'}`}
            >
              <div className={`absolute w-4 h-4 bg-white rounded-full shadow transition-transform duration-200
                ${form[key] ? 'translate-x-6' : 'translate-x-1'}`}
              />
            </div>
          </label>
        ))}
      </div>

      {form.is_password_protected && (
        <div>
          <label className="text-sm font-medium text-ink/80 block mb-1">Gallery Password</label>
          <input
            type="password"
            className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200"
            placeholder="Leave blank to keep existing"
            value={form.password}
            onChange={set('password')}
          />
        </div>
      )}

      <Button type="submit" loading={saving} className="w-fit">Save Settings</Button>
    </form>
  )
}
