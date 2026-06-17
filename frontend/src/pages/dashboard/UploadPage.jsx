import { useEffect, useState, useRef, useCallback } from 'react'
import { galleriesApi } from '../../api/galleriesApi'
import api from '../../api/axiosInstance'
import DropZone from '../../components/ui/DropZone'

// ── CONSTANTS ─────────────────────────────────────────────────────────────────
const ACCEPTED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif'])
const MAX_FILE_SIZE  = 20 * 1024 * 1024   // 20 MB per file
const MAX_FILES      = 50                  // max files per batch

// ── HELPERS ───────────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024)          return `${bytes} B`
  if (bytes < 1024 * 1024)   return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Validates a File against type and size constraints.
 * Returns an error message string, or null if the file is valid.
 */
function validateFile(file) {
  if (!ACCEPTED_TYPES.has(file.type)) {
    return `${file.name}: unsupported format (JPG, PNG, WEBP, GIF, AVIF only)`
  }
  if (file.size > MAX_FILE_SIZE) {
    return `${file.name}: file too large (max ${formatBytes(MAX_FILE_SIZE)})`
  }
  return null
}

// ── COMPONENT ─────────────────────────────────────────────────────────────────
export default function UploadPage() {
  // Gallery list state
  const [galleries,     setGalleries]     = useState([])
  const [galleriesLoading, setGalleriesLoading] = useState(true)
  const [galleriesError,   setGalleriesError]   = useState(null)
  const [selectedGalleryId, setSelectedGalleryId] = useState('')

  // File queue: { id, file, preview, progress, status, error }
  // status: 'idle' | 'uploading' | 'success' | 'error'
  const [queue,     setQueue]     = useState([])
  const [uploading, setUploading] = useState(false)

  // Validation errors shown above the dropzone
  const [validationErrors, setValidationErrors] = useState([])

  // Track blob URLs so we can revoke them on unmount
  const blobUrlsRef = useRef([])
  const isMountedRef = useRef(false)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      // Revoke all blob previews to free browser memory
      blobUrlsRef.current.forEach(url => URL.revokeObjectURL(url))
    }
  }, [])

  // ── Load galleries ──────────────────────────────────────────────────────────
  useEffect(() => {
    setGalleriesLoading(true)
    setGalleriesError(null)
    galleriesApi.getGalleries()
      .then(data => {
        const all = data.results || []
        setGalleries(all)
        if (all.length) setSelectedGalleryId(all[0].id)
      })
      .catch(() => {
        setGalleriesError('Failed to load galleries. Refresh to try again.')
      })
      .finally(() => setGalleriesLoading(false))
  }, [])

  // ── Handle files dropped / selected ────────────────────────────────────────
  const handleFiles = useCallback((files) => {
    const errors = []
    const valid  = []

    // Enforce max-files cap
    const remaining = MAX_FILES - queue.length
    const incoming  = files.slice(0, remaining)

    if (files.length > remaining) {
      errors.push(`Max ${MAX_FILES} files per upload. ${files.length - remaining} file(s) ignored.`)
    }

    for (const file of incoming) {
      const err = validateFile(file)
      if (err) {
        errors.push(err)
        continue
      }
      const preview = URL.createObjectURL(file)
      blobUrlsRef.current.push(preview)
      valid.push({
        id:       crypto.randomUUID(),
        file,
        preview,
        progress: 0,
        status:   'idle',
        error:    null,
      })
    }

    setValidationErrors(errors)
    if (valid.length) setQueue(prev => [...prev, ...valid])
  }, [queue.length])

  // ── Remove a single file from the queue ────────────────────────────────────
  const removeFile = useCallback((fileId) => {
    setQueue(prev => {
      const item = prev.find(f => f.id === fileId)
      if (item?.preview) {
        URL.revokeObjectURL(item.preview)
        blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== item.preview)
      }
      return prev.filter(f => f.id !== fileId)
    })
  }, [])

  // ── Clear entire queue ──────────────────────────────────────────────────────
  const clearQueue = useCallback(() => {
    queue.forEach(item => {
      if (item.preview) {
        URL.revokeObjectURL(item.preview)
        blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== item.preview)
      }
    })
    setQueue([])
    setValidationErrors([])
  }, [queue])

  // ── Retry only failed files ─────────────────────────────────────────────────
  const retryFailed = useCallback(() => {
    setQueue(prev => prev.map(f => f.status === 'error'
      ? { ...f, status: 'idle', progress: 0, error: null }
      : f
    ))
  }, [])

  // ── Upload all idle files ───────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!selectedGalleryId || uploading) return
    const idleFiles = queue.filter(f => f.status === 'idle')
    if (!idleFiles.length) return

    setUploading(true)

    for (const item of idleFiles) {
      if (!isMountedRef.current) break

      // Mark uploading
      setQueue(prev => prev.map(f =>
        f.id === item.id ? { ...f, status: 'uploading', progress: 0 } : f
      ))

      const formData = new FormData()
      formData.append('image',         item.file)
      formData.append('gallery',       selectedGalleryId)
      formData.append('original_name', item.file.name)
      formData.append('file_size',     item.file.size)

      try {
        await api.post('/photos/', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          params:  { gallery: selectedGalleryId },
          onUploadProgress: (evt) => {
            if (!isMountedRef.current) return
            const pct = evt.total
              ? Math.round((evt.loaded * 100) / evt.total)
              : 0
            setQueue(prev => prev.map(f =>
              f.id === item.id ? { ...f, progress: pct } : f
            ))
          },
        })

        if (isMountedRef.current) {
          setQueue(prev => prev.map(f =>
            f.id === item.id ? { ...f, status: 'success', progress: 100 } : f
          ))
        }
      } catch (err) {
        if (isMountedRef.current) {
          const msg = err.response?.data?.image?.[0]
            || err.response?.data?.detail
            || 'Upload failed'
          setQueue(prev => prev.map(f =>
            f.id === item.id ? { ...f, status: 'error', progress: 0, error: msg } : f
          ))
        }
      }
    }

    if (isMountedRef.current) setUploading(false)
  }

  // ── Derived counts ──────────────────────────────────────────────────────────
  const idleCount    = queue.filter(f => f.status === 'idle').length
  const successCount = queue.filter(f => f.status === 'success').length
  const errorCount   = queue.filter(f => f.status === 'error').length
  const totalCount   = queue.length

  const selectedGallery = galleries.find(g => g.id === selectedGalleryId)

  // ── RENDER ──────────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 720, animation: 'fadeUp 0.5s ease both' }}>

      {/* Page header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          fontFamily: 'Cormorant Garamond, serif',
          fontSize: 'clamp(26px, 4vw, 36px)',
          fontWeight: 400,
          color: 'var(--ink)',
          letterSpacing: '-0.5px',
          lineHeight: 1.1,
          marginBottom: 6,
        }}>
          Upload Photos
        </h1>
        <p style={{ fontSize: 13, color: 'var(--muted)', fontFamily: 'Outfit, sans-serif' }}>
          Select a gallery, drop your photos, and upload. Up to {MAX_FILES} photos per batch.
        </p>
      </div>

      {/* ── Step 1: Gallery selector ───────────────────────────────────────── */}
      <div style={{
        background: '#fff',
        border: '1px solid var(--warm)',
        borderRadius: 16,
        padding: '20px 24px',
        marginBottom: 16,
      }}>
        <label
          htmlFor="target-gallery"
          style={{
            display: 'block',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.6px',
            textTransform: 'uppercase',
            color: 'var(--ink2)',
            marginBottom: 8,
            fontFamily: 'Outfit, sans-serif',
          }}
        >
          Target Gallery
        </label>

        {galleriesLoading ? (
          <div className="skeleton" style={{ height: 44, borderRadius: 9 }} />
        ) : galleriesError ? (
          <div role="alert" style={{
            padding: '10px 14px', background: 'rgba(192,72,58,0.06)',
            border: '1px solid rgba(192,72,58,0.18)', borderRadius: 9,
            fontSize: 13, color: 'var(--red)', fontFamily: 'Outfit, sans-serif',
          }}>
            {galleriesError}
          </div>
        ) : galleries.length === 0 ? (
          <div style={{
            padding: '10px 14px', background: 'rgba(193,127,62,0.06)',
            border: '1px solid rgba(193,127,62,0.20)', borderRadius: 9,
            fontSize: 13, color: 'var(--accent)', fontFamily: 'Outfit, sans-serif',
          }}>
            No galleries yet.{' '}
            <a href="/dashboard/galleries" style={{ color: 'var(--accent)', fontWeight: 600, textDecoration: 'underline' }}>
              Create one first →
            </a>
          </div>
        ) : (
          <select
            id="target-gallery"
            value={selectedGalleryId}
            onChange={e => setSelectedGalleryId(e.target.value)}
            disabled={uploading}
            style={{
              width: '100%',
              padding: '11px 14px',
              background: '#fff',
              border: '1.5px solid var(--warm)',
              borderRadius: 9,
              fontSize: 14,
              color: 'var(--ink)',
              fontFamily: 'Outfit, sans-serif',
              outline: 'none',
              cursor: 'pointer',
              appearance: 'auto',
              opacity: uploading ? 0.6 : 1,
            }}
          >
            {galleries.map(g => (
              <option key={g.id} value={g.id}>
                {g.title}{g.photo_count != null ? ` — ${g.photo_count} photos` : ''}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* ── Step 2: Drop zone ──────────────────────────────────────────────── */}
      <div style={{ marginBottom: 16 }}>
        <DropZone
          onFiles={handleFiles}
          disabled={uploading || !selectedGalleryId || galleriesLoading}
          label="Drop photos to upload"
          multiple
        >
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: 52, height: 52,
              background: 'rgba(193,127,62,0.08)',
              border: '1px solid rgba(193,127,62,0.20)',
              borderRadius: 14,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 14px',
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--ink)', marginBottom: 4, fontFamily: 'Outfit, sans-serif' }}>
              Drop photos here
            </p>
            <p style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'Outfit, sans-serif' }}>
              or click to browse · JPG, PNG, WEBP, GIF, AVIF · max {formatBytes(MAX_FILE_SIZE)} each
            </p>
          </div>
        </DropZone>
      </div>

      {/* Validation errors */}
      {validationErrors.length > 0 && (
        <div role="alert" style={{
          padding: '10px 14px', marginBottom: 16,
          background: 'rgba(192,72,58,0.06)',
          border: '1px solid rgba(192,72,58,0.18)',
          borderRadius: 9, fontSize: 13, color: 'var(--red)',
          fontFamily: 'Outfit, sans-serif',
        }}>
          {validationErrors.map((err, i) => <div key={i}>⚠ {err}</div>)}
        </div>
      )}

      {/* ── Step 3: File queue ─────────────────────────────────────────────── */}
      {queue.length > 0 && (
        <div style={{
          background: '#fff',
          border: '1px solid var(--warm)',
          borderRadius: 16,
          overflow: 'hidden',
          marginBottom: 16,
        }}>
          {/* Queue header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '14px 20px',
            borderBottom: '1px solid var(--warm)',
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', fontFamily: 'Outfit, sans-serif' }}>
              {totalCount} {totalCount === 1 ? 'photo' : 'photos'} queued
              {successCount > 0 && (
                <span style={{ color: 'var(--green)', marginLeft: 10 }}>
                  ✓ {successCount} uploaded
                </span>
              )}
              {errorCount > 0 && (
                <span style={{ color: 'var(--red)', marginLeft: 10 }}>
                  ✗ {errorCount} failed
                </span>
              )}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              {errorCount > 0 && !uploading && (
                <button
                  type="button"
                  onClick={retryFailed}
                  style={{
                    fontSize: 12, fontWeight: 500, color: 'var(--accent)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: '4px 8px', borderRadius: 6,
                    fontFamily: 'Outfit, sans-serif',
                  }}
                >
                  Retry failed
                </button>
              )}
              {!uploading && (
                <button
                  type="button"
                  onClick={clearQueue}
                  style={{
                    fontSize: 12, fontWeight: 500, color: 'var(--muted)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: '4px 8px', borderRadius: 6,
                    fontFamily: 'Outfit, sans-serif',
                  }}
                >
                  Clear all
                </button>
              )}
            </div>
          </div>

          {/* File list */}
          <div style={{ maxHeight: 380, overflowY: 'auto' }}>
            {queue.map(item => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 20px',
                  borderBottom: '1px solid var(--cream2)',
                }}
              >
                {/* Thumbnail */}
                <div style={{
                  width: 44, height: 44, borderRadius: 8, overflow: 'hidden',
                  background: 'var(--cream2)', flexShrink: 0,
                  border: '1px solid var(--warm)',
                }}>
                  <img
                    src={item.preview}
                    alt=""
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    loading="lazy"
                  />
                </div>

                {/* File info + progress */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    marginBottom: item.status === 'uploading' ? 6 : 0,
                  }}>
                    <span style={{
                      fontSize: 13, color: 'var(--ink)', fontWeight: 500,
                      fontFamily: 'Outfit, sans-serif',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      maxWidth: '65%',
                    }}>
                      {item.file.name}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'Outfit, sans-serif', flexShrink: 0 }}>
                      {formatBytes(item.file.size)}
                    </span>
                  </div>

                  {/* Progress bar — only while uploading */}
                  {item.status === 'uploading' && (
                    <div style={{
                      height: 4, background: 'var(--warm)', borderRadius: 4, overflow: 'hidden',
                    }}>
                      <div style={{
                        height: '100%',
                        width: `${item.progress}%`,
                        background: 'linear-gradient(90deg, var(--accent), var(--accent2))',
                        borderRadius: 4,
                        transition: 'width 0.2s ease',
                      }} />
                    </div>
                  )}

                  {/* Error message */}
                  {item.status === 'error' && item.error && (
                    <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 2, fontFamily: 'Outfit, sans-serif' }}>
                      {item.error}
                    </p>
                  )}
                </div>

                {/* Status indicator */}
                <div style={{ flexShrink: 0, width: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {item.status === 'idle' && (
                    <button
                      type="button"
                      onClick={() => removeFile(item.id)}
                      disabled={uploading}
                      title="Remove"
                      aria-label={`Remove ${item.file.name}`}
                      style={{
                        background: 'none', border: 'none',
                        color: 'var(--sand)', cursor: 'pointer', padding: 2,
                        borderRadius: 4, transition: 'color 0.15s',
                        opacity: uploading ? 0.4 : 1,
                      }}
                      onMouseEnter={e => e.currentTarget.style.color = 'var(--red)'}
                      onMouseLeave={e => e.currentTarget.style.color = 'var(--sand)'}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                        aria-hidden="true">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                      </svg>
                    </button>
                  )}
                  {item.status === 'uploading' && (
                    <svg className="spinner" aria-label="Uploading…" style={{
                      width: 14, height: 14,
                      border: '2px solid rgba(193,127,62,0.25)',
                      borderTopColor: 'var(--accent)',
                      borderRadius: '50%',
                      animation: 'spin 0.7s linear infinite',
                    }} />
                  )}
                  {item.status === 'success' && (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                      stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                      aria-label="Uploaded">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  )}
                  {item.status === 'error' && (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                      stroke="var(--red)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                      aria-label="Failed">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Upload button ──────────────────────────────────────────────────── */}
      {queue.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button
            type="button"
            onClick={handleUpload}
            disabled={uploading || idleCount === 0 || !selectedGalleryId}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '12px 28px',
              background: 'var(--ink)',
              color: 'var(--cream)',
              border: 'none',
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 500,
              fontFamily: 'Outfit, sans-serif',
              cursor: (uploading || idleCount === 0 || !selectedGalleryId) ? 'not-allowed' : 'pointer',
              opacity: (uploading || idleCount === 0 || !selectedGalleryId) ? 0.55 : 1,
              transition: 'all 0.18s ease',
            }}
          >
            {uploading ? (
              <>
                <span style={{
                  width: 14, height: 14,
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: '#fff',
                  borderRadius: '50%',
                  display: 'inline-block',
                  animation: 'spin 0.7s linear infinite',
                }} />
                Uploading…
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                Upload {idleCount > 0 ? `${idleCount} Photo${idleCount > 1 ? 's' : ''}` : 'Photos'}
              </>
            )}
          </button>

          {/* Summary pill */}
          {selectedGallery && !uploading && (
            <span style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'Outfit, sans-serif' }}>
              → <strong style={{ color: 'var(--ink)' }}>{selectedGallery.title}</strong>
            </span>
          )}
        </div>
      )}

      {/* ── Success summary (all done) ──────────────────────────────────────── */}
      {!uploading && totalCount > 0 && idleCount === 0 && (
        <div style={{
          marginTop: 20,
          padding: '14px 20px',
          background: successCount === totalCount
            ? 'rgba(74,124,111,0.08)'
            : 'rgba(193,127,62,0.08)',
          border: `1px solid ${successCount === totalCount
            ? 'rgba(74,124,111,0.20)'
            : 'rgba(193,127,62,0.25)'}`,
          borderRadius: 12,
          fontSize: 13,
          fontFamily: 'Outfit, sans-serif',
          color: successCount === totalCount ? 'var(--green)' : 'var(--accent)',
        }}>
          {successCount === totalCount
            ? `✓ All ${successCount} photos uploaded successfully to "${selectedGallery?.title}".`
            : `${successCount} of ${totalCount} uploaded. ${errorCount} failed — click "Retry failed" to try again.`
          }
        </div>
      )}
    </div>
  )
}