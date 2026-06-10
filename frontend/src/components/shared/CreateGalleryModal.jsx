import { useState, useEffect, useLayoutEffect, useRef } from 'react'

/**
 * WHAT: Create Gallery Modal Overlay
 * WHY:  Handles user inputs to instantiate new collections. Encapsulates state resets,
 *       locking mechanisms, and full WCAG 2.1 keyboard focus trapping.
 *
 * CHANGELOG (eighth-round refinements):
 *   [F1] submittingRef sync effect gains [submitting] dependency array — the bare
 *        useEffect() with no deps ran after every render (every keystroke in the title
 *        field). Adding [submitting] confines it to the only renders that matter.
 *   [F2] Compound guard &&-logic clarified — isMountedRef and submittingRef serve
 *        distinct, non-overlapping failure modes. isMountedRef guards against parent
 *        page navigation unmounting the component mid-flight. submittingRef is solely
 *        for the keydown listener (reads current submitting state without re-registering).
 *        In catch/finally the correct single guard is isMountedRef.current only, since
 *        submittingRef.current is always true during the async operation and adds no
 *        new information to the guard condition.
 *   [F3] Removed redundant aria-busy from the submit button — the dialog container
 *        already carries aria-busy={submitting} (added in round 7). Keeping it on the
 *        button too causes NVDA and VoiceOver to announce "busy" twice: once for the
 *        region, once for the focused element. Button-level aria-busy removed.
 *   [F4] submittingRef sync switched from useEffect to useLayoutEffect — useEffect
 *        runs after paint, leaving a one-frame window where the ref lags state. The
 *        comment already promised layout-effect timing; the code now delivers it.
 */

// ── MODULE-LEVEL KEYFRAME INJECTION ──────────────────────────────────────────
// Injected once when the module loads to prevent <head> tag accumulation across
// repeated modal open/close cycles.
if (typeof document !== 'undefined') {
  const KEYFRAME_ID = 'modal-fade-up-keyframes'
  if (!document.getElementById(KEYFRAME_ID)) {
    const style = document.createElement('style')
    style.id = KEYFRAME_ID
    style.textContent = `
      @media (prefers-reduced-motion: no-preference) {
        @keyframes modalFadeUp {
          from { opacity: 0; transform: translateY(10px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
      }
    `
    document.head.appendChild(style)
  }
}

export default function CreateGalleryModal({ isOpen, onClose, onCreateSubmit }) {
  const [title,        setTitle]        = useState('')
  const [color,        setColor]        = useState('#000000')
  const [downloadable, setDownloadable] = useState(false)
  const [submitting,   setSubmitting]   = useState(false)
  const [errorMsg,     setErrorMsg]     = useState('')
  const [titleInvalid, setTitleInvalid] = useState(false)

  const modalRef      = useRef(null)
  const titleInputRef = useRef(null)

  // Lifecycle mount tracker — guards against parent page navigation unmounting the
  // component while an API call is still in-flight (e.g. user clicks Logout mid-submit).
  // This is distinct from isOpen toggling, which keeps the component mounted.
  const isMountedRef = useRef(false)
  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  // Ref mirror of submitting — lets the keydown listener read the current value
  // without needing to re-register the listener on every state change.
  // [F4] useLayoutEffect guarantees the ref is current before the next paint,
  //      matching the timing the Escape-key handler depends on.
  // [F1] Dependency array [submitting] — only syncs on the renders that matter,
  //      not on every keystroke the user types in the title field.
  const submittingRef = useRef(false)
  useLayoutEffect(() => {
    submittingRef.current = submitting
  }, [submitting])

  // Synchronously update the ref during render to eliminate the 1-render stale window.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  // ── RESET STATE ON OPEN ───────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return
    setTitle('')
    setColor('#000000')
    setDownloadable(false)
    setErrorMsg('')
    setTitleInvalid(false)
  }, [isOpen])

  // ── AUTO-FOCUS ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return
    const frame = requestAnimationFrame(() => titleInputRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [isOpen])

  // ── BODY SCROLL LOCK ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [isOpen])

  // ── KEYBOARD INTERACTION & WCAG FOCUS TRAP ────────────────────────────────
  // Dependency array is [isOpen] only — submitting is read via submittingRef so the
  // listener never tears down and re-registers on submitting state transitions.
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (!submittingRef.current) onCloseRef.current()
        return
      }

      if (e.key === 'Tab' && modalRef.current) {
        const focusable = Array.from(
          modalRef.current.querySelectorAll(
            [
              'button:not([disabled])',
              'input:not([disabled])',
              'select:not([disabled])',
              'textarea:not([disabled])',
              'a[href]:not([aria-disabled="true"])',
              '[tabindex]:not([tabindex="-1"]):not([disabled])',
            ].join(', ')
          )
        )
        if (!focusable.length) return

        const first = focusable[0]
        const last  = focusable[focusable.length - 1]

        if (!modalRef.current.contains(document.activeElement)) {
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

  // ── SUBMIT HANDLER ────────────────────────────────────────────────────────
  // Defined above the early-return guard — it IS part of the render closure and
  // captures current state values (title, color, downloadable) from this render.
  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!title.trim()) {
      setErrorMsg('Collection title is required.')
      setTitleInvalid(true)
      return
    }

    setSubmitting(true)
    setErrorMsg('')
    setTitleInvalid(false)

    try {
      await onCreateSubmit({
        title:           title.trim(),
        branding_color:  color,
        is_downloadable: downloadable,
      })

      // Happy path: no state writes follow onCloseRef.current(), so parent
      // unmounting here (e.g. navigating away on success) is safe.
      onCloseRef.current()
    } catch (err) {
      // [F2] Guard is isMountedRef.current only — this is the correct single gate
      //      for the unmount scenario. submittingRef.current is always true here
      //      (it hasn't been re-synced yet) so ANDing it adds no protection and
      //      only obscures which ref is doing the actual guarding work.
      if (isMountedRef.current) {
        setErrorMsg(err.message || 'Failed to initialize collection.')
      }
    } finally {
      // Same single guard — isMountedRef covers both isOpen=false-while-mounted
      // AND actual parent unmount. That is its entire job.
      if (isMountedRef.current) {
        setSubmitting(false)
      }
    }
  }

  // Early return — safely after all hook definitions.
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      aria-busy={submitting}
    >
      {/* Backdrop — locked during API transactions. Uses stable ref pointer. */}
      <div
        className="absolute inset-0 bg-gray-900/40 backdrop-blur-sm"
        onClick={submitting ? undefined : () => onCloseRef.current()}
        aria-hidden="true"
      />

      {/* Modal Card */}
      <div
        ref={modalRef}
        className="relative bg-white w-full max-w-md rounded-2xl border border-gray-200 shadow-xl p-6 z-10 overflow-hidden"
        style={{ animation: 'modalFadeUp 0.18s ease-out both' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-gray-100 mb-5">
          <h2
            id="modal-title"
            className="text-base font-semibold text-gray-900 tracking-tight"
          >
            Create New Gallery
          </h2>
          <button
            type="button"
            onClick={() => onCloseRef.current()}
            disabled={submitting}
            className="text-gray-400 hover:text-gray-600 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Close modal"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18" height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6"  x2="6"  y2="18" />
              <line x1="6"  y1="6"  x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div
            id="gallery-title-error"
            role="alert"
            className="mb-4 px-3 py-2 bg-red-50 border border-red-200 text-xs text-red-700 rounded-lg"
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-4">

          {/* Title Input */}
          <div className="flex flex-col gap-1">
            <label
              className="text-xs font-semibold text-gray-700"
              htmlFor="new-gallery-title"
            >
              Collection Title
            </label>
            <input
              ref={titleInputRef}
              id="new-gallery-title"
              type="text"
              placeholder="e.g. Elena Portrait Session"
              value={title}
              maxLength={100}
              aria-required="true"
              aria-invalid={titleInvalid}
              aria-describedby="gallery-title-error"
              onChange={(e) => {
                setTitle(e.target.value)
                if (errorMsg)     setErrorMsg('')
                if (titleInvalid) setTitleInvalid(false)
              }}
              disabled={submitting}
              className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-100 focus:ring-offset-0 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Color Picker */}
          <div className="flex flex-col gap-1">
            <label
              className="text-xs font-semibold text-gray-700"
              htmlFor="new-gallery-color"
            >
              Primary Brand Accent
            </label>
            <div className="flex items-center gap-3">
              <input
                id="new-gallery-color"
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                disabled={submitting}
                aria-describedby="color-hex-display"
                className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer overflow-hidden p-0 bg-transparent disabled:cursor-not-allowed"
              />
              <span
                id="color-hex-display"
                className="text-xs text-gray-500 font-medium font-mono uppercase"
                aria-live="polite"
              >
                {color}
              </span>
            </div>
          </div>

          {/* Download Toggle */}
          <div className="flex items-center gap-2 pt-2">
            <input
              id="new-gallery-download"
              type="checkbox"
              checked={downloadable}
              onChange={(e) => setDownloadable(e.target.checked)}
              disabled={submitting}
              className="w-4 h-4 rounded border-gray-300 text-gray-900 focus:ring-gray-900 disabled:cursor-not-allowed cursor-pointer"
            />
            <label
              className="text-xs font-semibold text-gray-700 cursor-pointer select-none"
              htmlFor="new-gallery-download"
            >
              Enable full-size downloads for clients
            </label>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100 mt-6">
            <button
              type="button"
              onClick={() => onCloseRef.current()}
              disabled={submitting}
              className="px-4 py-2 border border-gray-200 text-gray-700 hover:text-gray-900 hover:bg-gray-50 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            {/* [F3] aria-busy removed from button — the dialog container already carries
                 aria-busy={submitting}, which broadcasts to the entire region. Keeping it
                 here too causes NVDA/VoiceOver to announce "busy" twice. */}
            <button
              type="submit"
              disabled={submitting || !title.trim()}
              className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? 'Creating…' : 'Create Gallery'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}