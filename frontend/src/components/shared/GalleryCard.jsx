import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * WHAT: Individual Gallery Card Component
 * WHY:  Renders collection metrics, handles image load error fallbacks, and
 *       provides quick-actions for deletes, publishes, and copy-link triggers.
 *
 * Self-contained: reads the authenticated photographer's username directly
 * from the auth store, removing the need to prop-drill it from every parent.
 */
export default function GalleryCard({ gallery, onPublishToggle, onDeleteClick }) {
  const [copied, setCopied]     = useState(false)
  const [imgError, setImgError] = useState(false)
  const copyTimeoutRef          = useRef(null)

  // Subscribe only to the username slice; ?? null prevents falsy-string fallbacks
  // during auth store hydration (avoids corrupted /g/undefined/slug URLs)
  const username = useAuthStore((state) => state.user?.username ?? null)

  // FIX 1 (Bug 1 from Document 3): Extract cover_url BEFORE the early return
  // so the reset effect below can legitimately subscribe to it as a dependency.
  // gallery?.cover_url is safe here even when gallery is null/undefined.
  const coverUrl = gallery?.cover_url ?? null

  // ── ALL EFFECTS HOISTED — must live above every early return ────────────────

  // Effect A: Release the timer handle when the card unmounts.
  // Without this, the setCopied(false) callback fires on a dead component
  // if the user navigates away within 2 s of copying.
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  // Effect B (FIX 1): Reset the image error flag whenever the cover URL changes.
  //
  //   Scenario A — cover updated: after a photographer uploads a new cover,
  //   cover_url changes but imgError remains true from the previous 404,
  //   permanently blocking the new valid image behind the placeholder.
  //
  //   Scenario B — list reuse with index keys: when a gallery is deleted, React
  //   may hand a new gallery object to the same card position. The stale
  //   imgError from the previous card's broken asset then hides the new gallery's
  //   valid cover until a full remount. This effect clears it proactively.
  useEffect(() => {
    setImgError(false)
  }, [coverUrl])

  // ── EARLY RETURN — all hooks already called above, Rules of Hooks satisfied ─
  if (!gallery) return null

  // cover_url excluded from destructuring; use the already-derived coverUrl instead
  const { title, slug, photo_count, is_published, has_password, branding_color } = gallery

  // clientGalleryURL is null until the auth store confirms a real username,
  // which disables the copy button and prevents silent broken-link copies
  const clientGalleryURL = username
    ? `${window.location.protocol}//${window.location.host}/g/${username}/${slug}`
    : null

  // ── EVENT HANDLERS ──────────────────────────────────────────────────────────

  const handleCopyLink = async (e) => {
    e.stopPropagation()
    if (!clientGalleryURL) return

    try {
      await navigator.clipboard.writeText(clientGalleryURL)
      setCopied(true)
      // Clear any previous countdown before starting a fresh one
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy public link:', err)
    }
  }

  // type="button" outside a <form> carries no default browser action;
  // stopPropagation is the only meaningful call needed here
  const handlePublishToggle = (e) => {
    e.stopPropagation()
    onPublishToggle?.(slug, !is_published)
  }

  const handleDeleteClick = (e) => {
    e.stopPropagation()
    onDeleteClick?.(slug)
  }

  const showPlaceholder = !coverUrl || imgError
  const count           = photo_count ?? 0

  // FIX 2: Three-state aria-label for the copy button.
  // Previously it was two-state (available / unavailable), never updating when
  // copied=true. Screen readers would announce "Copy public gallery link" even
  // while the checkmark icon was showing, creating a verbal / visual mismatch.
  const copyAriaLabel = !clientGalleryURL
    ? 'Public link unavailable'
    : copied
      ? 'Link copied!'
      : 'Copy public gallery link'

  return (
    <div className="group border border-gray-200 rounded-2xl overflow-hidden bg-white shadow-sm flex flex-col h-full hover:shadow-md hover:border-gray-300 transition-all duration-200">

      {/* ── CARD COVER HEADER ────────────────────────────────────────────────── */}
      <div className="relative aspect-[3/2] w-full bg-gray-100 overflow-hidden border-b border-gray-100">
        {!showPlaceholder ? (
          <img
            src={coverUrl}
            alt={`${title} cover preview`}
            loading="lazy"
            onError={() => setImgError(true)}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 ease-out"
          />
        ) : (
          /* Branded color background + camera icon when no valid cover exists */
          <div
            className="w-full h-full flex items-center justify-center text-white/30"
            style={{ backgroundColor: branding_color || '#1a1a1a' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
          </div>
        )}

        {/* Floating status badges */}
        <div className="absolute top-3 left-3 flex flex-col gap-1.5 z-10">
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border shadow-sm ${
            is_published
              ? 'bg-green-50 text-green-700 border-green-200'
              : 'bg-yellow-50 text-yellow-700 border-yellow-200'
          }`}>
            {is_published ? 'Published' : 'Draft'}
          </span>

          {has_password && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-900/90 text-white border border-gray-800 shadow-sm backdrop-blur-sm">
              <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              Locked
            </span>
          )}
        </div>
      </div>

      {/* ── CARD BODY METADATA ───────────────────────────────────────────────── */}
      <div className="p-5 flex-1 flex flex-col justify-between">
        <div>
          <h3 className="text-base font-semibold text-gray-900 tracking-tight leading-snug line-clamp-1">
            {title}
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {count} {count === 1 ? 'photo' : 'photos'}
          </p>
        </div>

        {/* ── INTERACTIVE ACTION ROW ───────────────────────────────────────────── */}
        <div className="flex items-center justify-between pt-4 mt-5 border-t border-gray-100 gap-4">
          <div className="flex items-center gap-2">

            {/* Action 1: Copy Link */}
            <button
              type="button"
              onClick={handleCopyLink}
              disabled={!clientGalleryURL}
              aria-label={copyAriaLabel}
              title={clientGalleryURL ? 'Copy public link to clipboard' : 'Sign-in required to copy link'}
              className="p-1.5 rounded-lg border border-transparent transition-all cursor-pointer
                text-gray-400 hover:text-gray-600 hover:bg-gray-50 hover:border-gray-200
                disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent
                disabled:hover:border-transparent disabled:hover:text-gray-400"
            >
              {copied ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
              )}
            </button>

            {/* Action 2: Quick-Publish Toggle */}
            <button
              type="button"
              onClick={handlePublishToggle}
              aria-label={is_published ? 'Unpublish gallery' : 'Publish gallery'}
              title={is_published ? 'Unpublish (set to draft)' : 'Publish collection'}
              className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
                is_published
                  ? 'text-green-600 hover:text-green-700 bg-green-50 border-green-200'
                  : 'text-gray-400 hover:text-gray-600 bg-white border-gray-200 hover:bg-gray-50'
              }`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>

            {/* Action 3: Quick Delete */}
            <button
              type="button"
              onClick={handleDeleteClick}
              aria-label="Delete gallery"
              title="Delete collection"
              className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-all cursor-pointer"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                <line x1="10" y1="11" x2="10" y2="17"/>
                <line x1="14" y1="11" x2="14" y2="17"/>
              </svg>
            </button>
          </div>

          {/* Manage route link */}
          <Link
            to={`/dashboard/galleries/${slug}`}
            className="text-xs font-semibold text-gray-900 hover:text-gray-700 tracking-tight inline-flex items-center gap-1 hover:underline"
          >
            Manage
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </Link>
        </div>
      </div>
    </div>
  )
}