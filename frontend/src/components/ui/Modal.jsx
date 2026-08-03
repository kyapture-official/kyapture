// File Location: frontend/src/components/ui/Modal.jsx

import { useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

// ── KEYFRAME INJECTION ────────────────────────────────────────────────────────
// Injected once at module load — prevents duplicate <style> tags across
// repeated open/close cycles and React HMR.
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
// Tab focus trap in sync, preventing selector mismatches.
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
 * WHAT: Fully accessible, viewport-relative modal dialog via React Portal.
 *
 * Renders via createPortal(…, document.body) — BUG FIX from AI Studio:
 *   This breaks out of any CSS transform or filter on a parent <main> or
 *   layout container that would otherwise shift a `fixed` child off-centre
 *   (CSS Containing Block override). Solves the mobile off-centre issue.
 *
 * @param {boolean}           props.open     - Controls visibility
 * @param {Function}          props.onClose  - Called on backdrop click / Escape
 * @param {string}            [props.title]  - Header text
 * @param {React.ReactNode}   props.children - Modal content
 * @param {'sm'|'md'|'lg'|'xl'} [props.size='md'] - Width constraint
 */
export default function Modal({ open, onClose, title, children, size = 'md' }) {
  const modalRef  = useRef(null)
  const onCloseRef = useRef(onClose)

  // Stable ref so event-handler closures always see the latest onClose
  // without adding it to effect dependency arrays (which would re-register
  // listeners on every render).
  useLayoutEffect(() => {
    onCloseRef.current = onClose
  })

  // ── BODY SCROLL LOCK ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  // ── AUTO-FOCUS & FOCUS RESTORATION ────────────────────────────────────────
  // Captures the trigger element before opening so focus returns cleanly on
  // close — essential for keyboard and screen reader users.
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

  // ── KEYBOARD INTERACTION & FOCUS TRAP (WCAG 2.1 SC 2.1.2) ────────────────
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

      // Recover if focus drifts outside the modal (e.g. browser toolbar)
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

  // ── PORTAL — renders to document.body ─────────────────────────────────────
  // BUG FIX (AI Studio improvement, kept): createPortal breaks the modal
  // out of any parent CSS transform/filter, guaranteeing viewport-relative
  // centering on all screen sizes.
  //
  // WHY animation uses modalFadeUp, not toastSlideUp (AI Studio bug):
  //   toastSlideUp is injected by Toast.jsx. If no toast is mounted,
  //   the keyframe doesn't exist and the animation silently fails.
  //   modalFadeUp has its own injection above — always available.
  return createPortal(
    // Outer shell: positioning only, no ARIA role (avoids double-scoping)
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">

      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        onClick={() => onCloseRef.current?.()}
        aria-hidden="true"
      />

      {/* Modal card — role="dialog" belongs HERE (the perceived boundary),
          NOT on the outer positioning div. Placing it on the outer div
          scopes the dialog region to the full viewport, confusing screen readers. */}
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
              type="button"
              onClick={() => onCloseRef.current?.()}
              className="p-1.5 rounded-lg hover:bg-cream-200 text-muted transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-1"
              aria-label="Close modal"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor"
                viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round"
                  strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        )}
        <div className="p-6">{children}</div>
      </div>
    </div>,
    document.body
  )
}