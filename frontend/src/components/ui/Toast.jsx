import { createContext, useContext, useState, useCallback, useEffect, useLayoutEffect, useRef } from 'react'

// ── MODULE-LEVEL KEYFRAME INJECTION ──────────────────────────────────────────
// Injected once when the module loads to prevent head-tag accumulation
// across repeated toast open/close cycles [16].
if (typeof document !== 'undefined') {
  const KEYFRAME_ID = 'toast-fade-up-keyframes'
  if (!document.getElementById(KEYFRAME_ID)) {
    const style = document.createElement('style')
    style.id = KEYFRAME_ID
    style.textContent = `
      @media (prefers-reduced-motion: no-preference) {
        @keyframes toastFadeUp {
          from { opacity: 0; transform: translateY(12px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
      }
    `
    document.head.appendChild(style)
  }
}

const ToastCtx = createContext(null)

const icons = {
  success: '✓',
  error:   '✕',
  info:    'ℹ',
  warning: '⚠',
}

const colors = {
  success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  error:   'bg-red-50 border-red-200 text-red-800',
  info:    'bg-cream-100 border-cream-300 text-ink',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
}

/**
 * WHAT: Self-contained Toast Item with Scoped Timer Lifecycle
 * WHY:  Each item owns its own useEffect timer so clearTimeout fires automatically
 *       on unmount — no timer can fire setToasts against a dead component [12].
 */
function ToastItem({ toast, onDismiss }) {
  const { id, message, type } = toast

  const onDismissRef = useRef(onDismiss)
  
  // Safe Ref Sync: useLayoutEffect runs synchronously after DOM commit,
  // preventing stale closure execution without render-phase mutations [12].
  useLayoutEffect(() => {
    onDismissRef.current = onDismiss
  })

  useEffect(() => {
    const timer = setTimeout(() => onDismissRef.current(id), 3500)
    return () => clearTimeout(timer)
  }, [id])

  return (
    // No role="status" here — the parent container's aria-live region handles
    // announcements. Adding role="status" on items while the container has
    // aria-live creates nested live regions, causing double-reads [10].
    <div
      className={[
        'flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg',
        'text-sm font-medium pointer-events-auto',
        colors[type] || colors.info,
      ].filter(Boolean).join(' ')}
      style={{ animation: 'toastFadeUp 0.2s ease-out both' }}
    >
      <span className="font-bold" aria-hidden="true">
        {icons[type] || icons.info}
      </span>
      <span>{message}</span>
    </div>
  )
}

/**
 * WHAT: Centralized Notification Provider
 * WHY:  Houses active notification states and exposes a stable dispatch callback
 *       to let all sub-pages fire alerts with zero UI disruptions.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  // useRef for IDs — survives HMR without resetting, preventing key collisions [16]
  const idRef = useRef(0)

  const show = useCallback((message, type = 'info') => {
    idRef.current += 1
    const tid = idRef.current
    setToasts((t) => [...t, { id: tid, message, type }])
  }, [])

  const dismiss = useCallback((tid) => {
    setToasts((t) => t.filter((x) => x.id !== tid))
  }, [])

  return (
    <ToastCtx.Provider value={show}>
      {children}
      {/* aria-live="polite" — always rendered in the DOM so the browser registers
          the live region before any toasts appear [10].
          aria-atomic is intentionally omitted to prevent re-reading visible list items [10]. */}
      <div
        aria-live="polite"
        className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => {
  const context = useContext(ToastCtx)
  // Check context !== null to support out-of-provider execution protections [26]
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}