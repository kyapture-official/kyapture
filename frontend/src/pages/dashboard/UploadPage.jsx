import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useGalleries } from '../../hooks/useGalleries'
import { photosApi } from '../../api/photosApi'
import DropZone from '../../components/ui/DropZone'
import Spinner from '../../components/ui/Spinner'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

/**
 * WHAT: Centralized Bulk Photo Upload Page
 * WHY:  Allows photographers to select any active gallery container, drop batches
 *       of local image files, track upload progress, and safely abort in-flight uploads.
 */
export default function UploadPage() {
  const { galleries, loading: galleriesLoading, error: galleriesError } = useGalleries()

  const [selectedSlug, setSelectedSlug] = useState('')
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [successCount, setSuccessCount] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')

  const isMountedRef = useRef(false)
  const abortControllerRef = useRef(null)

  // Track mounting lifecycle to prevent setState calls on unmounted component
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [])

  // Auto-select the first available gallery in the list once loaded
  useEffect(() => {
    if (galleries?.length > 0 && !selectedSlug) {
      setSelectedSlug(galleries[0].slug)
    }
  }, [galleries, selectedSlug])

  /**
   * WHAT: File Upload Dispatcher
   * WHY:  Builds multipart FormData payloads, tracks progress in real-time,
   *       and supports in-flight cancellations safely via AbortController.
   */
  const handleFilesSelected = useCallback(async (files) => {
    // Guard against empty drops, missing gallery selection, or duplicate trigger
    if (!files?.length || !selectedSlug || uploading) return

    setUploading(true)
    setProgress(0)
    setSuccessCount(0)
    setErrorMsg('')

    // Instantiate a fresh AbortController so each upload batch can be cancelled independently
    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    // Build the standardized multipart payload
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('images', file)
    })

    // ── OFFLINE MOCK SYSTEM PATHWAY ──────────────────────────────────────────
    if (USE_MOCK_DATA) {
      try {
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError')

        // Simulated chunk-by-chunk upload sequence
        await new Promise((resolve, reject) => {
          let currentProgress = 0
          
          const onAbort = () => {
            clearInterval(timer)
            signal.removeEventListener('abort', onAbort) // Symmetrical cleanup on reject path
            reject(new DOMException('Aborted', 'AbortError'))
          }

          const timer = setInterval(() => {
            currentProgress += Math.floor(Math.random() * 20) + 10
            if (currentProgress >= 100) {
              currentProgress = 100
              clearInterval(timer)
              signal.removeEventListener('abort', onAbort) // Symmetrical cleanup on resolve path
              resolve()
            } else {
              if (isMountedRef.current) setProgress(currentProgress)
            }
          }, 300)

          signal.addEventListener('abort', onAbort)
        })

        if (isMountedRef.current) {
          setProgress(100)
          setSuccessCount(files.length)
        }
      } catch (err) {
        if (err.name === 'AbortError') return
        if (isMountedRef.current) {
          setErrorMsg('Simulation error: Upload could not be completed.')
        }
      } finally {
        if (isMountedRef.current) setUploading(false)
      }
      return
    }

    // ── PRODUCTION LIVE API PATHWAY ──────────────────────────────────────────
    try {
      const response = await photosApi.uploadBulk(
        selectedSlug,
        formData,
        (percent) => {
          if (isMountedRef.current) setProgress(percent)
        },
        signal
      )
      if (isMountedRef.current) {
        setSuccessCount(response.length || files.length)
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || 'Upload failed. Please verify S3 cloud configs.')
      }
    } finally {
      // isMountedRef guards against unmounted updates — no signal.aborted check needed here.
      // Removing that check was the fix for the frozen-spinner bug: after Cancel,
      // signal.aborted is true, which previously blocked setUploading(false) from ever running.
      if (isMountedRef.current) {
        setUploading(false)
      }
    }
  }, [selectedSlug, uploading])

  const handleCancelUpload = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }, [])

  const activeGallery = galleries?.find(g => g.slug === selectedSlug)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeUp">

      {/* HEADER SECTION */}
      <div className="pb-6 border-b border-gray-200 mb-8">
        <h1 className="text-2xl font-semibold text-gray-900 tracking-tight font-sans">
          Central Photo Uploader
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          Select a gallery container and drop your photos to upload them directly.
        </p>
      </div>

      {errorMsg && (
        <div role="alert" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans">
          {errorMsg}
        </div>
      )}

      {galleriesLoading ? (
        <div className="min-h-[30vh] flex items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : galleriesError ? (
        <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
          {galleriesError}
        </div>
      ) : galleries.length === 0 ? (
        /* Onboarding Empty State Fallback */
        <div className="py-16 text-center border-2 border-dashed border-gray-200 rounded-2xl bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900">No destination galleries found</h3>
          <p className="text-xs text-gray-500 mt-1 mb-6">You must build at least one empty collection before uploading images.</p>
          <Link to="/dashboard/galleries" className="px-4 py-2 bg-gray-900 text-white text-xs font-semibold rounded-lg hover:bg-gray-800 transition-colors">
            Create a Gallery First
          </Link>
        </div>
      ) : (
        /* Core Upload Interface Card */
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-6">

          {/* Gallery Dropdown Picker */}
          <div className="flex flex-col gap-1 max-w-sm">
            <label className="text-xs font-semibold text-gray-700" htmlFor="target-gallery-select">
              Destination Gallery
            </label>
            <select
              id="target-gallery-select"
              value={selectedSlug}
              onChange={(e) => setSelectedSlug(e.target.value)}
              disabled={uploading}
              className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 bg-white focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-100 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {galleries.map((g) => (
                <option key={g.id} value={g.slug}>
                  {g.title} ({g.is_published ? 'Published' : 'Draft'})
                </option>
              ))}
            </select>
          </div>

          {/* Interactive Upload Area */}
          {!uploading && successCount === 0 && (
            <DropZone onFiles={handleFilesSelected} disabled={uploading} />
          )}

          {/* Active Uploading Progress Tracker */}
          {uploading && (
            <div className="border border-gray-200 rounded-2xl p-6 bg-gray-50/50 flex flex-col items-center justify-center text-center space-y-4 animate-fadeUp">
              <div className="relative w-16 h-16 flex items-center justify-center">
                {/* viewBox="0 0 64 64" maps coordinate units 1:1 to the w-16/h-16 (64px) container,
                    preventing ring clipping in Safari and Firefox */}
                <svg
                  className="absolute inset-0 w-full h-full -rotate-90"
                  viewBox="0 0 64 64"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <circle cx="32" cy="32" r="28" stroke="#e5e7eb" strokeWidth="4" fill="transparent" />
                  <circle
                    cx="32" cy="32" r="28"
                    stroke="#111827" strokeWidth="4" fill="transparent"
                    strokeDasharray={`${2 * Math.PI * 28}`}
                    strokeDashoffset={`${2 * Math.PI * 28 * (1 - progress / 100)}`}
                    className="transition-all duration-150 ease-out"
                  />
                </svg>
                <span className="text-xs font-bold text-gray-900 font-mono">{progress}%</span>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-gray-900">Streaming Assets to S3</h4>
                <p className="text-xs text-gray-500 mt-1 max-w-xs">
                  Please keep this browser window open. We are compressing and organizing your files.
                </p>
              </div>

              {/* Cancel Button */}
              <button
                type="button"
                onClick={handleCancelUpload}
                className="px-3 py-1.5 border border-red-200 hover:border-red-300 text-red-600 hover:text-red-700 bg-white text-xs font-medium rounded-lg transition-colors cursor-pointer"
              >
                Cancel Upload
              </button>
            </div>
          )}

          {/* Success Summary Alert */}
          {successCount > 0 && (
            <div className="border border-green-200 bg-green-50 rounded-2xl p-6 text-center flex flex-col items-center justify-center space-y-4 animate-fadeUp">
              <div aria-hidden="true" className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center text-green-600">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-green-800">Upload Complete!</h4>
                <p className="text-xs text-green-600 mt-1">
                  Successfully imported <strong>{successCount}</strong> photos into "{activeGallery?.title}".
                </p>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setSuccessCount(0)}
                  className="px-3 py-1.5 border border-green-300 text-green-700 hover:bg-green-100 text-xs font-medium rounded-lg transition-colors cursor-pointer"
                >
                  Upload More
                </button>
                <Link
                  to={`/dashboard/galleries/${selectedSlug}`}
                  className="px-3 py-1.5 bg-green-700 text-white hover:bg-green-800 text-xs font-medium rounded-lg transition-colors text-center"
                  style={{ textDecoration: 'none' }}
                >
                  View Gallery
                </Link>
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  )
}
