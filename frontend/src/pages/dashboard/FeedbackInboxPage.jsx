// File Location: frontend/src/pages/dashboard/FeedbackInboxPage.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../../components/ui/Toast'
import Spinner from '../../components/ui/Spinner'
import { feedbackApi } from '../../api/feedbackApi'
import {
  describeFeedbackError,
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUSES,
  labelOf,
} from '../../utils/feedbackFlow'
import { formatDateTime, timeAgo } from '../../utils/formatters'

const PAGE_SIZE = 20          // the server's default page size for this list
const LONG_MESSAGE = 320      // characters before a message is collapsed behind "Show more"

const selectClass =
  'rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500'

const STATUS_TONE = {
  new: 'bg-amber-50 text-amber-800 border-amber-200',
  reviewed: 'bg-cream-100 text-ink border-cream-300',
  in_progress: 'bg-sky-50 text-sky-800 border-sky-200',
  resolved: 'bg-brand-green-50 text-brand-green-800 border-brand-green-200',
  dismissed: 'bg-cream-50 text-muted border-cream-200',
}

const isCancelled = (err) => err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'

/**
 * Everything user-written here (subject, message, username, email, route) is
 * rendered as React text children, which are always escaped. There is no
 * dangerouslySetInnerHTML and no innerHTML anywhere in this page.
 */
function FeedbackItem({ item, saving, rowError, onStatusChange }) {
  const [expanded, setExpanded] = useState(false)
  const long = item.message.length > LONG_MESSAGE
  const who = item.username || item.user_email

  return (
    <li className="rounded-xl border border-cream-200 bg-surface-light p-4" data-testid="feedback-item">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h3 className={`break-words text-sm font-semibold ${item.subject ? 'text-ink' : 'italic text-muted'}`}>
            {item.subject || '(No subject)'}
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <span className="rounded-full border border-cream-300 bg-cream-50 px-2 py-0.5 font-medium text-ink">
              {labelOf(FEEDBACK_CATEGORIES, item.category)}
            </span>
            <span title={formatDateTime(item.created_at)}>{timeAgo(item.created_at)}</span>
            <span aria-hidden="true">·</span>
            <span className="break-all">{who}{item.username && item.user_email ? ` (${item.user_email})` : ''}</span>
          </p>
        </div>

        <div className="flex flex-shrink-0 flex-col sm:items-end">
          <label className="sr-only" htmlFor={`status-${item.id}`}>
            Status of feedback from {who}
          </label>
          <div className="flex items-center gap-2">
            {saving && <Spinner size="sm" />}
            <select
              id={`status-${item.id}`}
              value={item.status}
              disabled={saving}
              onChange={(event) => onStatusChange(item, event.target.value)}
              className={`${selectClass} border ${STATUS_TONE[item.status] || ''}`}
            >
              {FEEDBACK_STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
          {rowError && (
            <p role="alert" className="mt-1 max-w-[16rem] text-xs text-red-700 sm:text-right">{rowError}</p>
          )}
        </div>
      </div>

      <p
        className={`mt-3 whitespace-pre-wrap break-words text-sm text-ink/90 ${long && !expanded ? 'line-clamp-5' : ''}`}
      >
        {item.message}
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="mt-1 cursor-pointer rounded text-xs font-medium text-brand-green-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}

      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-cream-200 pt-2 text-[11px] text-muted">
        <span>Page: <span className="break-all font-mono">{item.route || 'not recorded'}</span></span>
        <span>Version: {item.app_version || 'not recorded'}</span>
        <span>Browser: {item.browser_class || 'other'}</span>
      </p>
    </li>
  )
}

export default function FeedbackInboxPage() {
  const user = useAuthStore((s) => s.user)
  const toast = useToast()
  const isStaff = user?.is_staff === true

  const [status, setStatus] = useState('')
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)        // { count, results }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [rowErrors, setRowErrors] = useState({})
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const result = await feedbackApi.inbox({ status, category, page }, signal)
      if (signal?.aborted || !isMountedRef.current) return
      setData(result)
      setRowErrors({})
    } catch (err) {
      if (isCancelled(err) || signal?.aborted || !isMountedRef.current) return
      setError(describeFeedbackError(err, 'inbox').message)
    } finally {
      if (!signal?.aborted && isMountedRef.current) setLoading(false)
    }
  }, [status, category, page])

  // Not staff: no request is made at all (the server would answer 403 anyway).
  useEffect(() => {
    if (!isStaff) return undefined
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [isStaff, load])

  const changeFilter = (setter) => (event) => {
    setter(event.target.value)
    setPage(1)
  }

  const handleStatusChange = async (item, nextStatus) => {
    if (savingId || nextStatus === item.status) return
    setSavingId(item.id)
    setRowErrors((current) => ({ ...current, [item.id]: '' }))
    try {
      const updated = await feedbackApi.setStatus(item.id, nextStatus)
      if (!isMountedRef.current) return
      setData((current) => current && ({
        ...current,
        results: current.results.map((row) => (row.id === item.id ? { ...row, ...updated } : row)),
      }))
      toast(`Marked ${labelOf(FEEDBACK_STATUSES, nextStatus).toLowerCase()}`, 'success')
    } catch (err) {
      if (!isMountedRef.current) return
      setRowErrors((current) => ({ ...current, [item.id]: describeFeedbackError(err, 'status').message }))
    } finally {
      if (isMountedRef.current) setSavingId(null)
    }
  }

  if (!isStaff) {
    return (
      <div className="mx-auto max-w-xl py-16 text-center" data-testid="feedback-inbox-denied">
        <h2 className="font-serif text-2xl text-ink">Staff only</h2>
        <p className="mt-2 text-sm text-muted">The feedback inbox is only available to KYAPTURE staff accounts.</p>
        <Link
          to="/dashboard"
          className="mt-5 inline-block rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2"
        >
          Back to overview
        </Link>
      </div>
    )
  }

  const results = data?.results ?? []
  const total = data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filtered = Boolean(status || category)

  return (
    <div className="mx-auto max-w-4xl" data-testid="feedback-inbox">
      <div className="mb-5">
        <h2 className="font-serif text-2xl text-ink">Feedback inbox</h2>
        <p className="mt-1 text-sm text-muted">Messages sent from the Send feedback button, newest first.</p>
      </div>

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="inbox-status" className="mb-1 block text-xs font-medium text-ink">Status</label>
          <select id="inbox-status" value={status} onChange={changeFilter(setStatus)} className={selectClass}>
            <option value="">All statuses</option>
            {FEEDBACK_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="inbox-category" className="mb-1 block text-xs font-medium text-ink">Category</label>
          <select id="inbox-category" value={category} onChange={changeFilter(setCategory)} className={selectClass}>
            <option value="">All categories</option>
            {FEEDBACK_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        {filtered && (
          <button
            type="button"
            onClick={() => { setStatus(''); setCategory(''); setPage(1) }}
            className="cursor-pointer rounded-lg px-3 py-2 text-sm text-muted hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
          >
            Clear filters
          </button>
        )}
        <p className="ml-auto text-xs text-muted" aria-live="polite">
          {data && !error ? `${total} message${total === 1 ? '' : 's'}` : ''}
        </p>
      </div>

      {error ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-6 text-center">
          <p className="text-sm text-red-800">{error}</p>
          <button
            type="button"
            onClick={() => load()}
            className="mt-3 cursor-pointer rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-cream-100"
          >
            Try again
          </button>
        </div>
      ) : loading && !data ? (
        <div role="status" className="flex items-center justify-center gap-3 py-16 text-sm text-muted">
          <Spinner size="md" /> Loading feedback…
        </div>
      ) : results.length === 0 ? (
        <div className="rounded-xl border border-dashed border-cream-300 px-6 py-14 text-center" data-testid="feedback-empty">
          <p className="text-sm text-ink">{filtered ? 'No feedback matches these filters.' : 'No feedback yet.'}</p>
          <p className="mt-1 text-xs text-muted">
            {filtered ? 'Try a different status or category.' : 'New messages will appear here and in the bell.'}
          </p>
        </div>
      ) : (
        <>
          <ul className={`space-y-3 transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
            {results.map((item) => (
              <FeedbackItem
                key={item.id}
                item={item}
                saving={savingId === item.id}
                rowError={rowErrors[item.id]}
                onStatusChange={handleStatusChange}
              />
            ))}
          </ul>

          {pageCount > 1 && (
            <nav aria-label="Feedback pages" className="mt-5 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="cursor-pointer rounded-lg border border-cream-300 px-3 py-1.5 text-sm text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-muted">Page {page} of {pageCount}</span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={page >= pageCount || loading}
                className="cursor-pointer rounded-lg border border-cream-300 px-3 py-1.5 text-sm text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
