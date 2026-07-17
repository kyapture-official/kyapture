// File Location: frontend/src/components/shared/PasswordModal.jsx

import React, {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useCallback,
  useMemo,
  useId,
} from 'react'
import PropTypes from 'prop-types'
import Spinner from '../ui/Spinner'

// Selector used by the Tab focus trap to enumerate keyboard-reachable elements.
// Explicitly excludes disabled controls and elements with tabindex="-1"
// (programmatic-only focus targets like the dialog container itself).
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), textarea:not([disabled]), ' +
  '[tabindex]:not([tabindex="-1"])'

// ---------------------------------------------------------------------------
// Icon sub-components — stable memo refs; aria-hidden keeps them out of the
// accessibility tree so they are never double-announced with button labels.
// ---------------------------------------------------------------------------

const EyeIcon = React.memo(() => (
  <svg
    className="w-5 h-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    aria-hidden="true"
  >
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
))
EyeIcon.displayName = 'EyeIcon'

const EyeSlashIcon = React.memo(() => (
  <svg
    className="w-5 h-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    aria-hidden="true"
  >
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
  </svg>
))
EyeSlashIcon.displayName = 'EyeSlashIcon'

const WarningIcon = React.memo(() => (
  <svg
    className="w-3.5 h-3.5 flex-shrink-0"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    aria-hidden="true"
  >
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
))
WarningIcon.displayName = 'WarningIcon'

// ---------------------------------------------------------------------------
// PasswordModal
//
// Renders the dialog panel only — no backdrop or scroll lock. Those are
// owned by ClientGalleryPage.jsx, which already wraps this in a
// scroll-locked viewport container. Don't add a backdrop here.
//
// @requires React 18+ (useId)
// ---------------------------------------------------------------------------

export default function PasswordModal({
  open,
  onSubmit,
  error   = null,
  loading = false,
  onClose,
}) {
  const uid = useId()
  const ids = useMemo(() => ({
    title : `${uid}title`,
    input : `${uid}input`,
    error : `${uid}error`,
  }), [uid])

  const [password,     setPassword    ] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const containerRef     = useRef(null)   // dialog root; receives focus during loading
  const inputRef         = useRef(null)   // primary input; receives focus on open/error
  const previousFocusRef = useRef(null)   // element focused before modal opened (restored on close)

  // Mirrors `loading` prop into a ref so Effect 2's keydown handler can read
  // the current value without re-subscribing on every loading toggle.
  const loadingRef     = useRef(loading)
  // Tracks loading → idle transitions so Effect 3 can distinguish
  // "initial render with loading=false" from "just finished loading".
  // Reset at the top of every open cycle in Effect 1 (see note there).
  const prevLoadingRef = useRef(false)

  // Mirrors `onClose` into a ref so Effect 2 doesn't need it as a dependency,
  // avoiding listener churn when the parent passes an unmemoized callback.
  const onCloseRef = useRef(onClose)

  // `loadingRef`'s mirror MUST be a layout effect, declared before Effect 1.
  // Effect 1 (also a layout effect) reads loadingRef.current synchronously,
  // in the same commit, to decide whether to autofocus the input on open. If
  // this mirror were a plain useEffect (passive — runs after paint), then on
  // any render where `open` and `loading` both flip to true at once, Effect 1
  // would run first and read the *previous* render's loading value, since
  // the passive mirror hasn't had a chance to update it yet. Declaration
  // order between layout effects in the same commit is guaranteed, so
  // putting this one first fixes the staleness outright.
  useLayoutEffect(() => { loadingRef.current = loading }, [loading])
  // `onClose` has no layout-effect consumer — Effect 2 only reads onCloseRef
  // later, inside an async keydown handler, well after any commit has
  // flushed — so a plain passive mirror is correct and cheaper here.
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  // ── Effect 1: state reset + initial focus ──────────────────────────────
  // Resets all form state on every open cycle and defers programmatic focus
  // to rAF so it fires after the first browser paint.
  // Cleanup restores focus to the pre-modal element when the dialog closes.
  //
  // useLayoutEffect so that `previousFocusRef` is captured synchronously, in
  // declaration order, before Effect 3 below runs in the same commit. If the
  // modal can ever mount already in a loading state, Effect 3 moves focus to
  // the container — if that ran first, this effect would capture the
  // container itself as "the previously focused element" instead of
  // whatever the user was actually on before the dialog opened.
  useLayoutEffect(() => {
    if (!open) return

    previousFocusRef.current = document.activeElement
    setPassword('')
    setShowPassword(false)

    // Every fresh open starts clean. Without this, a session closed
    // externally while still loading (parent cancels, navigation, etc.)
    // leaves this flag stuck at `true`, so the *next* open would mistake a
    // fresh mount for "a load in this session just finished" and schedule a
    // redundant (harmless, but pointless) extra focus call on the input.
    prevLoadingRef.current = false

    // Skip the autofocus-input step if the dialog is opening directly into a
    // loading state — Effect 3 will focus the container instead, and we don't
    // want two effects fighting over where focus lands on the same commit.
    let raf
    if (!loadingRef.current) {
      raf = requestAnimationFrame(() => inputRef.current?.focus())
    }

    return () => {
      if (raf) cancelAnimationFrame(raf)
      previousFocusRef.current?.focus()  // restore caller's keyboard position
      previousFocusRef.current = null
    }
  }, [open])

  // ── Effect 2: keyboard — ESC dismissal + Tab focus trap ────────────────
  // Single consolidated handler. `loading` and `onClose` are read via refs so
  // this effect only needs to re-subscribe when `open` changes.
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e) => {
      // ESC: dismiss only when not mid-submission to prevent accidental close.
      if (e.key === 'Escape') {
        if (!loadingRef.current) onCloseRef.current?.()
        return
      }

      // TAB: keep focus cycling within the dialog's interactive elements.
      if (e.key === 'Tab') {
        const focusable = Array.from(
          containerRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) ?? []
        )

        // During loading, all controls are disabled → focusable is empty.
        // Block Tab entirely so focus cannot escape the container.
        if (focusable.length === 0) {
          e.preventDefault()
          return
        }

        const first = focusable[0]
        const last  = focusable[focusable.length - 1]

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open])

  // ── Effect 3: focus management across loading transitions ──────────────
  //
  // Focus Container During Loading:
  //   Disabling a focused element evicts focus to document.body synchronously,
  //   as part of the same DOM commit — no effect runs early enough to prevent
  //   that blur itself. What useLayoutEffect buys us is correcting focus back
  //   to the container before the *next paint*, so the browser never actually
  //   paints a frame with focus visibly sitting on <body>.
  //
  // Restore Focus to Input:
  //   Container now holds focus. Keyboard users are stranded on a
  //   non-interactive element. Detect the loading → idle transition via
  //   prevLoadingRef and restore focus to the input for immediate re-entry.
  //
  // Reads `loading` directly from the prop (not via a ref) — it's already
  // fresh for this render, no relay needed.
  useLayoutEffect(() => {
    if (!open) return

    if (loading) {
      prevLoadingRef.current = true
      containerRef.current?.focus()
    } else if (prevLoadingRef.current) {
      // loading just became false — failed auth or cancelled request.
      prevLoadingRef.current = false
      const raf = requestAnimationFrame(() => inputRef.current?.focus())
      return () => cancelAnimationFrame(raf)
    }
  }, [open, loading])

  const handlePasswordChange = useCallback(
    (e) => setPassword(e.target.value),
    [],
  )

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault()
      if (!password.trim() || loading) return
      // Called directly, not optional-chained: `onSubmit` is a required prop
      // (enforced via PropTypes below). If it's ever missing, failing loud
      // with a thrown TypeError — visible in error tracking, with a stack
      // trace pointing straight at this line — is far easier to diagnose
      // than a silent no-op where the button visibly does nothing.
      //
      // Submitted as-is, not trimmed: leading/trailing whitespace, if any,
      // is part of the password's value, not incidental input noise. The
      // `.trim()` check above is only an emptiness guard.
      onSubmit(password)
    },
    [password, loading, onSubmit],
  )

  const toggleShowPassword = useCallback(() => {
    // Per the WHATWG spec, selectionStart/selectionEnd/setSelectionRange are
    // explicitly supported for type="password" (along with text/search/url/
    // tel) — this isn't a known password-specific failure case. The guard
    // below is cheap insurance against the input's type ever changing to an
    // unsupported one in a future edit, not a fix for an existing bug — and
    // either way, it must never be able to block the toggle from firing.
    let selectionStart = null
    let selectionEnd   = null
    try {
      const node = inputRef.current
      selectionStart = node?.selectionStart ?? null
      selectionEnd   = node?.selectionEnd   ?? null
    } catch {
      // Treat as "nothing to restore" rather than letting this block the toggle.
    }

    setShowPassword((prev) => !prev)

    // Some engines reset caret position when an input's `type` flips between
    // "password" and "text". Restore it on the next frame, once the new type
    // has actually been applied to the DOM.
    if (selectionStart !== null && selectionEnd !== null) {
      requestAnimationFrame(() => {
        try {
          inputRef.current?.setSelectionRange(selectionStart, selectionEnd)
        } catch {
          // Non-fatal: worst case the caret lands at the default position.
        }
      })
    }
  }, [])

  if (!open) return null

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={ids.title}
      aria-busy={loading}             // Tells screen readers the dialog subtree is updating
      tabIndex={-1}                   // Allows programmatic focus; excluded from Tab order
      className="w-full max-w-sm mx-auto p-6 bg-white border border-cream-200 rounded-xl shadow-md focus:outline-none"
      style={{ animation: 'fadeUp 0.4s ease both' }}
    >
      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <div>
          <label
            id={ids.title}
            htmlFor={ids.input}
            className="block text-xs uppercase tracking-wider text-muted font-medium mb-2 select-none"
          >
            Enter Collection Password
          </label>

          <div className="relative rounded-lg shadow-sm">
            <input
              ref={inputRef}
              type={showPassword ? 'text' : 'password'}
              id={ids.input}
              name="gallery-password"
              value={password}
              onChange={handlePasswordChange}
              disabled={loading}
              required
              autoComplete="current-password"
              autoCapitalize="none"         // Matters once toggled to type="text": stops mobile keyboards suggesting caps on the now-visible field
              autoCorrect="off"             // Disables autocorrect on WebKit/Safari
              spellCheck={false}            // Disables spell-check when type="text"
              aria-invalid={!!error}
              aria-describedby={error ? ids.error : undefined}
              className="block w-full rounded-lg border border-cream-300 bg-cream-50/30 px-4 py-3 pr-10 text-sm text-ink placeholder-cream-400 focus:border-ink focus:bg-white focus:outline-none focus:ring-1 focus:ring-ink disabled:bg-cream-100 disabled:text-cream-400 transition-all duration-200"
              placeholder="••••••••"
            />

            <button
              type="button"
              onClick={toggleShowPassword}
              disabled={loading}
              aria-pressed={showPassword}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-cream-400 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-1 rounded-r-lg disabled:pointer-events-none transition-colors duration-200"
            >
              {showPassword ? <EyeSlashIcon /> : <EyeIcon />}
            </button>
          </div>
        </div>

        {/* Assertive live region interrupts screen readers immediately on auth
            failure. min-h-5 reserves height up front so the error mounting
            doesn't shift layout (CLS). */}
        <div className="min-h-5" aria-live="assertive" aria-atomic="true">
          {error && (
            <p
              id={ids.error}
              className="text-xs text-red-600 font-light flex items-center gap-1 select-none"
              style={{ animation: 'fadeUp 0.2s ease both' }}
            >
              <WarningIcon />
              {error}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={!password.trim() || loading}
          className="w-full relative flex items-center justify-center rounded-lg bg-ink px-4 py-3 text-sm font-medium tracking-wide text-white hover:bg-ink/90 active:scale-[0.98] disabled:bg-cream-200 disabled:text-cream-400 disabled:pointer-events-none focus:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 transition-all duration-200"
        >
          {/* Preserves element width during loading, preventing layout shifts */}
          <span className={loading ? 'invisible' : undefined}>
            Unlock Collection
          </span>

          {loading && (
            <>
              <span
                className="absolute inset-0 flex items-center justify-center"
                aria-hidden="true"
              >
                <Spinner className="w-5 h-5 text-cream-400" />
              </span>
              <span className="sr-only">Verifying password…</span>
            </>
          )}
        </button>
      </form>
    </div>
  )
}

PasswordModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onSubmit: PropTypes.func.isRequired,
  error: PropTypes.string,
  loading: PropTypes.bool,
  onClose: PropTypes.func,
}