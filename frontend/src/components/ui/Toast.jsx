// File Location: frontend/src/components/ui/Toast.jsx
// VERSION: Isomorphic Production — Week 10
// All bugs resolved. SSR environment safety guaranteed.

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useMemo,
} from 'react'

// ── ISOMORPHIC LAYOUT EFFECT ──────────────────────────────────────────────────
// Prevents standard React console warnings during SSR compilation runs by
// dynamically falling back to useEffect when 'window' is unavailable.
const useIsomorphicLayoutEffect =
  typeof window !== 'undefined' ? useLayoutEffect : useEffect

// ── KEYFRAME INJECTION ───────────────────────────────────────────────────────
if (typeof document !== 'undefined') {
  const KEYFRAME_ID = 'kyapture-toast-keyframes'
  if (!document.getElementById(KEYFRAME_ID)) {
    const style = document.createElement('style')
    style.id = KEYFRAME_ID
    style.textContent = `
      @media (prefers-reduced-motion: no-preference) {
        @keyframes toastSlideUp {
          from { opacity: 0; transform: translateY(10px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
      }
    `
    document.head.appendChild(style)
  }
}

// ── DESIGN TOKENS ────────────────────────────────────────────────────────────
const TYPE_STYLES = {
  success: 'bg-emerald-50  border-emerald-200 text-emerald-900',
  error:   'bg-red-50      border-red-200     text-red-900',
  warning: 'bg-amber-50    border-amber-200   text-amber-900',
  info:    'bg-cream-100   border-cream-300   text-ink',
  loading: 'bg-[#fdfbf7]   border-cream-300   text-ink',
}

const TYPE_ICON_COLOR = {
  success: 'text-green', // Custom brand green (#4a7c6f) from tailwind.config
  error:   'text-red-600',
  warning: 'text-amber-600',
  info:    'text-ink',
  loading: 'text-ink',
}

// ── SVG ICONS ─────────────────────────────────────────────────────────────────
function SuccessIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24"
      stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/>
    </svg>
  )
}
function ErrorIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24"
      stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/>
    </svg>
  )
}
function WarningIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24"
      stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
    </svg>
  )
}
function InfoIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24"
      stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
    </svg>
  )
}
function LoadingIcon({ className }) {
  return (
    <svg className={`animate-spin ${className}`} fill="none"
      viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10"
        stroke="currentColor" strokeWidth="3"/>
      <path className="opacity-75" fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
    </svg>
  )
}
function CloseIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24"
      stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/>
    </svg>
  )
}

const ICONS = {
  success: SuccessIcon,
  error:   ErrorIcon,
  warning: WarningIcon,
  info:    InfoIcon,
  loading: LoadingIcon,
}

// ── TOAST ITEM ────────────────────────────────────────────────────────────────
function ToastItem({ toast, onDismiss }) {
  const { id, message, type, duration } = toast
  const Icon      = ICONS[type]           ?? ICONS.info
  const iconColor = TYPE_ICON_COLOR[type] ?? TYPE_ICON_COLOR.info
  const cardColor = TYPE_STYLES[type]     ?? TYPE_STYLES.info

  const onDismissRef = useRef(onDismiss)
  useIsomorphicLayoutEffect(() => { onDismissRef.current = onDismiss })

  useEffect(() => {
    if (duration === 0) return
    const timer = setTimeout(() => onDismissRef.current(id), duration)
    return () => clearTimeout(timer)
  }, [id, duration])

  return (
    <div
      className={[
        'pointer-events-auto',
        'flex items-center gap-3 pl-4 pr-3 py-3',
        'rounded-xl border shadow-md text-sm font-medium',
        cardColor,
      ].join(' ')}
      style={{ animation: 'toastSlideUp 0.2s ease-out both' }}
    >
      <Icon className={`h-4 w-4 flex-shrink-0 ${iconColor}`} />
      <span className="leading-snug select-text flex-1">{message}</span>
      <button
        type="button"
        onClick={() => onDismiss(id)}
        className="text-current opacity-50 hover:opacity-100 transition-opacity cursor-pointer focus:outline-none flex-shrink-0 ml-1"
        aria-label="Dismiss notification"
      >
        <CloseIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

const ToastCtx = createContext(null)

// ── TOAST PROVIDER ────────────────────────────────────────────────────────────
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const show = useCallback((message, type = 'info', customDuration = null) => {
    idRef.current += 1
    const id = idRef.current
    const duration = customDuration != null
      ? customDuration
      : type === 'loading' ? 0 : 3500
    setToasts((t) => [...t, { id, message, type, duration }])
    return id
  }, [])

  const contextValue = useMemo(() => {
    const fn = (message, type = 'info', duration = null) =>
      show(message, type ?? 'info', duration ?? null)
    fn.dismiss = dismiss
    return fn
  }, [show, dismiss])

  return (
    <ToastCtx.Provider value={contextValue}>
      {children}
      <div
        aria-live="polite"
        aria-label="Notifications"
        className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none max-w-sm w-full"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}