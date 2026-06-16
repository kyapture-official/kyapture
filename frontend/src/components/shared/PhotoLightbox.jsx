import { useEffect, useLayoutEffect, useRef } from 'react'

// ── ISO-MORPHIC LAYEPUT EFFECT ──
// Safely executes useLayoutEffect in the browser and falls back to useEffect
// on the server to prevent console warnings during SSR compilation [13].
const useIsomorphicLayoutEffect =
  typeof window !== 'undefined' ? useLayoutEffect : useEffect

const FOCUSABLE = [
  'button:not([disabled])',
  'a[href]:not([aria-disabled="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
].join(', ')

/**
 * WHAT: Fullscreen Photo Lightbox Viewer
 * WHY:  Enables immersive, high-contrast, keyboard-navigable image browsing.
 *       Conforms strictly to W3C focus-containment and body-locking standards.
 */
export default function PhotoLightbox({ photos, currentIndex, onClose, onNavigate }) {
  const lightboxRef = useRef(null)

  const totalCount  = photos?.length ?? 0
  const activePhoto = photos?.[currentIndex]
  const isOpen      = totalCount > 0 && !!activePhoto

  // ── REF ASSIGNMENTS (Concurrent-safe) ─────────────────────────────────────
  const onCloseRef    = useRef(onClose)
  const onNavigateRef = useRef(onNavigate)
  const currentIndexRef = useRef(currentIndex)
  const totalCountRef   = useRef(totalCount) // Symmetrical initialization matching props [12]

  // No dependency array: intentional. This must mirror ALL prop changes into
  // the refs after every commit so that the stable [isOpen] event listener
  // always reads the latest values without a stale closure [12, 16].
  useIsomorphicLayoutEffect(() => {
    onCloseRef.current    = onClose
    onNavigateRef.current = onNavigate
    currentIndexRef.current = currentIndex
    totalCountRef.current   = totalCount
  })

  // ── BODY SCROLL LOCK ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [isOpen])

  // ── FOCUS CAPTURE & FOCUS RESTORATION ─────────────────────────────────────
  // Fired strictly once on open/close to prevent snapping focus mid-session [10]
  useEffect(() => {
    if (!isOpen) return
    const previouslyFocused = document.activeElement

    const frame = requestAnimationFrame(() => {
      const nextBtn  = lightboxRef.current?.querySelector('[aria-label="Next photo"]')
      const closeBtn = lightboxRef.current?.querySelector('[aria-label="Close lightbox"]')
      ;(nextBtn || closeBtn)?.focus()
    })

    return () => {
      cancelAnimationFrame(frame)
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus()
      }
    }
  }, [isOpen])

  // ── KEYBOARD CONTROLS & FOCUS TRAPPING ────────────────────────────────────
  // Stable [isOpen] dependency eliminates listener re-registration churn [16]
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onCloseRef.current?.()
        return
      }

      if (e.key === 'ArrowLeft') {
        if (currentIndexRef.current > 0) {
          onNavigateRef.current?.(currentIndexRef.current - 1)
        }
        return
      }

      if (e.key === 'ArrowRight') {
        if (currentIndexRef.current < totalCountRef.current - 1) {
          onNavigateRef.current?.(currentIndexRef.current + 1)
        }
        return
      }

      if (e.key === 'Tab' && lightboxRef.current) {
        const focusableEls = Array.from(
          lightboxRef.current.querySelectorAll(FOCUSABLE)
        )
        if (!focusableEls.length) return

        const first = focusableEls[0]
        const last  = focusableEls[focusableEls.length - 1]

        if (!lightboxRef.current.contains(document.activeElement)) {
          e.preventDefault()
          ;(e.shiftKey ? last : first).focus()
          return
        }

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div
      ref={lightboxRef}
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      className="fixed inset-0 z-50 bg-black/95 flex flex-col justify-between select-none animate-fadeUp p-4"
    >
      {/* ── TOP CONTROL PANEL ── */}
      <div className="flex items-center justify-between z-10 w-full pb-4 border-b border-white/10">
        <span className="text-xs font-semibold font-mono text-gray-400">
          {currentIndex + 1} of {totalCount}
        </span>

        <button
          type="button"
          onClick={() => onCloseRef.current?.()}
          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-1 focus-visible:ring-offset-black"
          aria-label="Close lightbox"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <line x1="18" y1="6"  x2="6"  y2="18" />
            <line x1="6"  y1="6"  x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* ── CENTER ACTIVE IMAGE DISPLAY AREA ── */}
      <div className="relative flex-1 flex items-center justify-center py-6 w-full max-h-[calc(100vh-140px)]">

        {/* Dynamic Screen-Reader Navigation Region [10]
            aria-live="polite" non-disruptively announces slide transitions,
            while aria-atomic="true" reads the entire string block cleanly [10]. */}
        <div
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {`Photo ${currentIndex + 1} of ${totalCount}${
            activePhoto.original_name ? `: ${activePhoto.original_name}` : ''
          }`}
        </div>

        {/* Left Arrow */}
        <button
          type="button"
          onClick={() => currentIndex > 0 && onNavigateRef.current?.(currentIndex - 1)}
          disabled={currentIndex === 0}
          className="absolute left-2 p-3 rounded-full bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors cursor-pointer z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          aria-label="Previous photo"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Core Image Asset */}
        <img
          src={activePhoto.image_url}
          alt={activePhoto.original_name || 'Gallery item'}
          className="max-w-full max-h-full object-contain pointer-events-none select-none rounded-sm shadow-2xl"
          draggable="false"
        />

        {/* Right Arrow */}
        <button
          type="button"
          onClick={() => currentIndex < totalCount - 1 && onNavigateRef.current?.(currentIndex + 1)}
          disabled={currentIndex === totalCount - 1}
          className="absolute right-2 p-3 rounded-full bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors cursor-pointer z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          aria-label="Next photo"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* ── BOTTOM METADATA BAR ── */}
      <div className="flex items-center justify-center py-4 border-t border-white/10 z-10 w-full">
        <p className="text-xs text-gray-400 font-medium truncate max-w-md">
          {activePhoto.original_name || 'Untitled Image'}
        </p>
      </div>
    </div>
  )
}
