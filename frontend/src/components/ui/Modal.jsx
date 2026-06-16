import { useEffect, useLayoutEffect, useRef } from 'react'

// ── MODULE-LEVEL KEYFRAME INJECTION ──────────────────────────────────────────
// Injected once when the module loads to prevent head-tag accumulation
// across repeated modal open/close cycles [16].
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

// Single source of truth for focusable elements — keeps auto-focus and the
// Tab focus trap in perfect sync, preventing edge-case selector mismatches [10].
const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'a[href]:not([aria-disabled="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
].join(', ')

const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

/**
 * WHAT: Reusable, Fully Accessible Modal Overlay
 * WHY:  Wraps content in a highly secure, keyboard-trapped, accessible container.
 *       Conforms strictly to WCAG 2.1 SC 2.1.2 focus-containment standards [10].
 *
 * @param {Object}      props
 * @param {boolean}     props.open     - If true, renders the modal card and backdrop
 * @param {Function}    props.onClose  - Callback function to execute on close triggers
 * @param {string}      [props.title]  - Optional title rendered inside the header
 * @param {React.ReactNode} props.children - Modal inner content
 * @param {'sm'|'md'|'lg'|'xl'} [props.size] - Target layout width constraint
 */
export default function Modal({ open, onClose, title, children, size = 'md' }) {
  const modalRef = useRef(null)
  const onCloseRef = useRef(onClose)

  // useLayoutEffect runs synchronously after DOM commit but before paint,
  // preventing stale closure execution without render-phase mutations [12].
  useLayoutEffect(() => {
    onCloseRef.current = onClose
  })

  // ── BODY SCROLL LOCK ──────────────────────────────────────────────────────
  // Locks background document scrolling to prevent trackpad shifts [10]
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  // ── AUTO-FOCUS & FOCUS RESTORATION ────────────────────────────────────────
  // Captures active trigger element before opening and restores focus cleanly on unmount [10].
  // Method-presence check handles both HTML and SVG elements via the HTMLOrSVGElement mixin [10].
  useEffect(() => {
    if (!open) return
    const previouslyFocused = document.activeElement

    const frame = requestAnimationFrame(() => {
      const first = modalRef.current?.querySelector(FOCUSABLE)
      first?.focus()
    })

    return () => {
      cancelAnimationFrame(frame)
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus()
      }
    }
  }, [open])

  // ── KEYBOARD INTERACTION & FOCUS TRAP ─────────────────────────────────────
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onCloseRef.current?.()
        return
      }

      if (e.key !== 'Tab' || !modalRef.current) return

      const focusable = Array.from(modalRef.current.querySelectorAll(FOCUSABLE))
      if (!focusable.length) return

      const first = focusable[0]
      const last  = focusable[focusable.length - 1]

      // Symmetrical Escape-recovery: respects Shift+Tab direction on out-of-modal clicks [10]
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

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  if (!open) return null

  return (
    // Positional shell only — deliberately carries no ARIA role.
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">

      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        onClick={() => onCloseRef.current?.()}
        aria-hidden="true"
      />

      {/* Modal Card
          role="dialog" + aria-modal live here — on the element the user
          perceives as the modal boundary — so screen readers correctly scope
          the dialog region to the card content, not the full viewport [10]. */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
        className={`relative bg-cream-50 rounded-2xl shadow-2xl w-full border border-cream-200 overflow-hidden ${widths[size]}`}
        style={{ animation: 'modalFadeUp 0.18s ease-out both' }}
      >
        {title && (
          <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-cream-200">
            <h3 id="modal-title" className="font-serif text-xl text-ink">
              {title}
            </h3>
            <button
              onClick={() => onCloseRef.current?.()}
              className="p-1.5 rounded-lg hover:bg-cream-200 text-muted transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-1"
              aria-label="Close modal"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}