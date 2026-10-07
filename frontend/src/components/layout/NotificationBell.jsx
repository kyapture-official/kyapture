// File Location: frontend/src/components/layout/NotificationBell.jsx
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, CreditCard, Download, Heart, Image as ImageIcon, MessageSquare, Rocket, ShieldAlert, TriangleAlert } from 'lucide-react'
import { notificationsApi } from '../../api/notificationsApi'
import { timeAgo } from '../../utils/formatters'

// How often the lightweight unread COUNT is refreshed while the tab is visible.
// Errors back the interval off (x2, capped) and a success resets it, so a
// failing/offline API is never hammered.
const POLL_MS = 60 * 1000
const MAX_BACKOFF_MS = 5 * 60 * 1000
const FOCUS_REFETCH_GUARD_MS = 5 * 1000

const KIND_ICON = {
  download: Download,
  favorite: Heart,
  payment: CreditCard,
  published: Rocket,
  processing_done: ImageIcon,
  processing_failed: TriangleAlert,
  feedback: MessageSquare,
  security: ShieldAlert,
}

/**
 * The dashboard notification bell. Everything shown comes from the server
 * (GET /notifications/): there are no built-in/demo entries, and read state is
 * persisted server-side, so it is the same after a refresh or on another device.
 *
 * Notifications are short pointers to recent events; the durable record of each
 * lives on its own page (Download Activity, Favorite Activity, Billing, ...) —
 * clicking a notification marks it read and opens that page.
 */
export default function NotificationBell() {
  const navigate = useNavigate()
  const panelId = useId()
  const triggerRef = useRef(null)
  const panelRef = useRef(null)
  const isMountedRef = useRef(true)

  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [markingAll, setMarkingAll] = useState(false)

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  // ── Lightweight unread-count polling (visible tab only, with backoff) ─────
  useEffect(() => {
    let timer = null
    let delay = POLL_MS
    let stopped = false
    let lastFetchAt = 0

    const refreshCount = async () => {
      lastFetchAt = Date.now()
      try {
        const data = await notificationsApi.unreadCount()
        if (!stopped && isMountedRef.current) setUnread(data.unread_count)
        delay = POLL_MS
      } catch {
        delay = Math.min(delay * 2, MAX_BACKOFF_MS)
      }
    }
    const schedule = () => {
      clearTimeout(timer)
      if (stopped) return
      timer = setTimeout(async () => {
        if (document.visibilityState === 'visible') await refreshCount()
        schedule()
      }, delay)
    }
    // Returning to a tab fires BOTH `visibilitychange` and `focus`; one fetch
    // is enough, so anything within a few seconds of the last fetch is skipped.
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastFetchAt > FOCUS_REFETCH_GUARD_MS) refreshCount()
    }

    refreshCount()
    schedule()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      stopped = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [])

  const loadPage = useCallback(async (nextPage, { replace }) => {
    setLoading(true)
    setError('')
    try {
      const data = await notificationsApi.list(nextPage)
      if (!isMountedRef.current) return
      setItems((prev) => (replace ? data.results : [...prev, ...data.results]))
      setPage(nextPage)
      setHasMore(Boolean(data.next))
      setUnread(data.unread_count)
    } catch {
      if (isMountedRef.current) setError('Could not load notifications.')
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [])

  const close = useCallback((returnFocus = true) => {
    setOpen(false)
    if (returnFocus) triggerRef.current?.focus()
  }, [])

  const toggle = () => {
    if (open) { close(false); return }
    setOpen(true)
    loadPage(1, { replace: true })        // the full list is only fetched when the panel opens
  }

  // Outside click and Escape close the panel.
  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (panelRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return
      close(false)
    }
    const onKeyDown = (event) => { if (event.key === 'Escape') close(true) }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, close])

  const handleOpenItem = async (item) => {
    if (!item.is_read) {
      try {
        const result = await notificationsApi.markRead(item.id)
        if (isMountedRef.current) {
          setItems((prev) => prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)))
          setUnread(result.unread_count)
        }
      } catch {
        /* the destination still opens; the item simply stays unread */
      }
    }
    close(false)
    navigate(item.link)
  }

  const handleMarkAll = async () => {
    if (markingAll || unread === 0) return
    setMarkingAll(true)
    try {
      const result = await notificationsApi.markAllRead()
      if (isMountedRef.current) {
        setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
        setUnread(result.unread_count)
      }
    } catch {
      if (isMountedRef.current) setError('Could not mark notifications as read.')
    } finally {
      if (isMountedRef.current) setMarkingAll(false)
    }
  }

  const badge = unread > 99 ? '99+' : String(unread)

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        className="relative cursor-pointer rounded-xl p-2 text-muted transition-all hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unread > 0 && (
          <span
            data-testid="notification-badge"
            className="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-surface-light"
          >
            {badge}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Notifications"
          className="fixed inset-x-3 top-16 z-50 overflow-hidden rounded-2xl border border-cream-200 bg-surface-light shadow-2xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96"
        >
          <div className="flex items-center justify-between border-b border-cream-200 px-4 py-3">
            <h2 className="font-serif text-lg text-ink">Notifications</h2>
            <button
              type="button"
              onClick={handleMarkAll}
              disabled={unread === 0 || markingAll}
              className="flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-brand-green-700 transition-colors hover:bg-brand-green-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Mark all as read
            </button>
          </div>

          <div className="max-h-[min(24rem,70vh)] overflow-y-auto" aria-live="polite">
            {loading && items.length === 0 ? (
              <p role="status" className="px-4 py-10 text-center text-sm text-muted">Loading…</p>
            ) : error && items.length === 0 ? (
              <div role="alert" className="px-4 py-8 text-center">
                <p className="text-sm text-red-700">{error}</p>
                <button
                  type="button"
                  onClick={() => loadPage(1, { replace: true })}
                  className="mt-3 cursor-pointer rounded-lg border border-cream-200 px-3 py-1.5 text-xs font-medium text-ink hover:bg-cream-100"
                >
                  Try again
                </button>
              </div>
            ) : items.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
                  <Bell className="h-5 w-5 text-muted" aria-hidden="true" />
                </div>
                <p className="text-sm text-ink">You're all caught up</p>
                <p className="mt-1 text-xs text-muted">Downloads, favorites and other activity will show up here.</p>
              </div>
            ) : (
              <ul>
                {items.map((item) => {
                  const Icon = KIND_ICON[item.kind] || Bell
                  return (
                    <li key={item.id} className="border-b border-cream-200 last:border-b-0">
                      <button
                        type="button"
                        onClick={() => handleOpenItem(item)}
                        className={`flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-cream-100 focus:bg-cream-100 focus:outline-none ${
                          item.is_read ? '' : 'bg-brand-green-50/50'
                        }`}
                      >
                        <span className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
                          item.kind === 'processing_failed' || item.kind === 'security' ? 'bg-red-50 text-red-600' : 'bg-cream-100 text-muted'
                        }`}>
                          <Icon className="h-4 w-4" aria-hidden="true" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={`block text-sm leading-snug ${item.is_read ? 'text-ink/80' : 'font-medium text-ink'}`}>
                            {item.message}
                          </span>
                          <span className="mt-0.5 block text-[11px] text-muted">{timeAgo(item.timestamp)}</span>
                        </span>
                        {!item.is_read && (
                          <span className="mt-2 h-2 w-2 flex-shrink-0 rounded-full bg-brand-green-600" aria-label="Unread" />
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {hasMore && (
            <div className="border-t border-cream-200 p-2">
              <button
                type="button"
                onClick={() => loadPage(page + 1, { replace: false })}
                disabled={loading}
                className="w-full cursor-pointer rounded-lg py-2 text-xs font-medium text-ink hover:bg-cream-100 disabled:opacity-50"
              >
                {loading ? 'Loading…' : 'Load older'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
