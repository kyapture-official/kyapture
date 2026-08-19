// File Location: frontend/src/pages/dashboard/GalleryPhotosPage.jsx
// VERSION: Gold-Standard Production — Week 12 (Audit Synced)
// Resolves Phase 1D silent-swallows, handles Promise.allSettled checks, and prevents memory leaks.

import React, { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { photosApi } from '../../api/photosApi'
import { useToast } from '../../components/ui/Toast'
import Spinner from '../../components/ui/Spinner'
import DropZone from '../../components/ui/DropZone'
import PhotoGrid from '../../components/shared/PhotoGrid'

export default function GalleryPhotosPage() {
  const { id: slug } = useParams() // Slug variable extracted from App.jsx route param
  const toast = useToast()

  const [photos, setPhotos]           = useState([])
  const [loading, setLoading]         = useState(true)
  const [submitting, setSubmitting]   = useState(false)
  const [uploadQueue, setUploadQueue] = useState([])

  const isMountedRef = useRef(false)
  const blobUrlsRef = useRef([]) // Tracks blob allocations to prevent page memory leaks

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      // Revoke all remaining upload preview blobs on unmount
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  // ── 1. LOAD GALLERY PHOTOS ─────────────────────────────────────────────────
  useEffect(() => {
    async function loadPhotos() {
      setLoading(true)
      try {
        const data = await photosApi.list(slug)
        if (isMountedRef.current) {
          setPhotos(data || [])
        }
      } catch {
        if (isMountedRef.current) {
          toast('Failed to load gallery photos.', 'error')
        }
      } finally {
        if (isMountedRef.current) setLoading(false)
      }
    }
    loadPhotos()
  }, [slug, toast])

  // ── 2. MULTIPART PHOTO UPLOAD ──────────────────────────────────────────────
  const handleFilesSelected = async (files) => {
    if (!files?.length) return

    setSubmitting(true)

    // Generate local preview blob URLs
    const queueItems = files.map((file) => {
      const previewUrl = URL.createObjectURL(file)
      blobUrlsRef.current.push(previewUrl)
      return { id: Math.random().toString(36).slice(2, 9), file, previewUrl, progress: 0 }
    })
    setUploadQueue((prev) => [...prev, ...queueItems])

    // Process files sequentially to maintain progress state precision
    for (const item of queueItems) {
      const formData = new FormData()
      formData.append('image', item.file)

      try {
        const uploaded = await photosApi.uploadBulk(
          slug,
          formData,
          (pct) => {
            if (isMountedRef.current) {
              setUploadQueue((prev) =>
                prev.map((q) => (q.id === item.id ? { ...q, progress: pct } : q))
              )
            }
          }
        )

        if (isMountedRef.current) {
          const newAssets = Array.isArray(uploaded) ? uploaded : [uploaded]
          setPhotos((prev) => [...prev, ...newAssets])
          setUploadQueue((prev) => prev.filter((q) => q.id !== item.id))

          // Deallocate success preview blob from browser memory
          URL.revokeObjectURL(item.previewUrl)
          blobUrlsRef.current = blobUrlsRef.current.filter((u) => u !== item.previewUrl)
        }
      } catch (err) {
        if (isMountedRef.current) {
          setUploadQueue((prev) =>
            prev.map((q) => (q.id === item.id ? { ...q, error: true } : q))
          )
          
          // Deallocate failed preview blobs too on eviction
          URL.revokeObjectURL(item.previewUrl)
          blobUrlsRef.current = blobUrlsRef.current.filter((u) => u !== item.previewUrl)
          
          const errorMsg = err.response?.data?.image?.[0] || `Failed to upload ${item.file.name}.`
          toast(errorMsg, 'error')
        }
      }
    }
    if (isMountedRef.current) setSubmitting(false)
  }

  // ── 3. PHOTO DELETION RESOLVER ─────────────────────────────────────────────
  const handleDeletePhoto = async (photoId) => {
    // Defensive rollback clone: Stores the exact, indexed state of active assets
    const originalPhotos = [...photos]
    setPhotos((prev) => prev.filter((p) => p.id !== photoId))

    try {
      const result = await photosApi.deletePhotos([photoId])

      // BUG RESOLUTION (Phase 1D): Because deletePhotos resolves Promise.allSettled successfully,
      // we must evaluate the returned payload's failed collection directly to detect S3 errors.
      if (result && result.failed && result.failed.length > 0) {
        // Restore original photos list to preserve layout order and notify the photographer
        if (isMountedRef.current) {
          setPhotos(originalPhotos)
          const errorText = result.failed[0]?.error || 'Deletion rejected by server.'
          toast(`Failed to delete photo: ${errorText}`, 'error')
        }
      } else {
        toast('Photo removed from collection.', 'success')
      }
    } catch {
      // Fallback for absolute transport-level failures (CORS, network drop)
      if (isMountedRef.current) {
        setPhotos(originalPhotos)
        toast('Network error occurred during photo deletion.', 'error')
      }
    }
  }

  if (loading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <Spinner size="lg" className="text-ink" />
      </div>
    )
  }

  return (
    <div className="space-y-6 font-sans">
      <header className="flex items-center justify-between pb-4 border-b border-cream-200">
        <div>
          <h2 className="font-serif text-2xl text-ink">Manage Photos</h2>
          <p className="text-xs text-muted">Upload and delete visual assets inside this collection [weekly tasks.txt].</p>
        </div>
        <Link to="/dashboard/galleries" className="text-xs font-semibold text-muted hover:text-ink transition-colors">
          ← Back to Collections
        </Link>
      </header>

      {/* Drag & Drop uploader component */}
      <DropZone onFiles={handleFilesSelected} disabled={submitting} />

      {/* In-progress upload queues progress bars */}
      {uploadQueue.length > 0 && (
        <div className="space-y-2 p-4 bg-cream-50/50 border border-cream-200 rounded-2xl animate-fadeUp">
          <h4 className="text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Upload Queue</h4>
          {uploadQueue.map((item) => (
            <div key={item.id} className="flex items-center gap-3">
              <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 bg-cream-100 border border-cream-200">
                <img src={item.previewUrl} alt="" className="w-full h-full object-cover" />
              </div>
              <div className="flex-1">
                <div className="text-xs text-ink truncate">{item.file.name}</div>
                <div className="h-1.5 bg-cream-200 rounded-full overflow-hidden mt-1">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${item.error ? 'bg-red-400' : 'bg-ink'}`}
                    style={{ width: `${item.error ? 100 : item.progress}%` }}
                  />
                </div>
              </div>
              <span className="text-[10px] text-muted flex-shrink-0">
                {item.error ? 'Failed' : `${item.progress}%`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Primary Visual Photo Grid with semantic tab controls */}
      <div className="pt-4">
        <PhotoGrid photos={photos} onDelete={handleDeletePhoto} showActions />
      </div>
    </div>
  )
}