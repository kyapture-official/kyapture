// File Location: frontend/src/pages/dashboard/StaffAuditPage.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import Spinner from '../../components/ui/Spinner'
import StaffGate from '../../components/shared/StaffGate'
import { staffApi } from '../../api/staffApi'
import { AUDIT_ACTIONS, describeStaffError, STAFF_PAGE_SIZE } from '../../utils/staffFlow'
import { formatDateTime } from '../../utils/formatters'

const selectClass =
  'rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500'

const isCancelled = (err) => err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'

/**
 * Read only: the page has no control that adds, edits or removes a row, and the API has no such
 * route. Everything shown (emails, the reason a staff member typed) is rendered as React text,
 * which is always escaped.
 */
function Actor({ row }) {
  if (row.actor_email) return <span className="break-all">{row.actor_email}</span>
  return <span className="text-muted">{row.action.startsWith('security.') ? 'System / visitor' : 'System'}</span>
}

function Target({ row }) {
  if (row.target_email) return <span className="break-all">{row.target_email}</span>
  return <span className="text-muted">None</span>
}

function AuditTable({ rows }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm" data-testid="audit-table">
        <thead>
          <tr className="border-b border-cream-200 text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-medium">When</th>
            <th className="py-2 pr-4 font-medium">Who</th>
            <th className="py-2 pr-4 font-medium">What</th>
            <th className="py-2 pr-4 font-medium">Target</th>
            <th className="py-2 pr-4 font-medium">Address</th>
            <th className="py-2 font-medium">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-cream-100 align-top" data-testid="audit-row">
              <td className="whitespace-nowrap py-3 pr-4 text-muted">{formatDateTime(row.created_at)}</td>
              <td className="max-w-[13rem] py-3 pr-4 text-ink"><Actor row={row} /></td>
              <td className="py-3 pr-4 text-ink">{row.action_label}</td>
              <td className="max-w-[13rem] py-3 pr-4 text-ink"><Target row={row} /></td>
              <td className="whitespace-nowrap py-3 pr-4 font-mono text-xs text-muted">{row.ip || 'none'}</td>
              <td className="max-w-[18rem] break-words py-3 text-muted">{row.reason || 'none'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AuditList({ rows }) {
  return (
    <ul className="divide-y divide-cream-200 border-y border-cream-200 md:hidden" data-testid="audit-list">
      {rows.map((row) => (
        <li key={row.id} className="space-y-1 py-4 text-sm" data-testid="audit-row">
          <p className="font-medium text-ink">{row.action_label}</p>
          <p className="text-xs text-muted">{formatDateTime(row.created_at)}</p>
          <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">Who</dt><dd className="text-right text-ink"><Actor row={row} /></dd>
            <dt className="text-muted">Target</dt><dd className="text-right text-ink"><Target row={row} /></dd>
            <dt className="text-muted">Address</dt><dd className="text-right font-mono text-muted">{row.ip || 'none'}</dd>
            <dt className="text-muted">Reason</dt><dd className="break-words text-right text-muted">{row.reason || 'none'}</dd>
          </dl>
        </li>
      ))}
    </ul>
  )
}

function AuditPageBody() {
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const result = await staffApi.audit({ action, page }, signal)
      if (signal?.aborted || !mounted.current) return
      setData(result)
    } catch (err) {
      if (isCancelled(err) || signal?.aborted || !mounted.current) return
      setData(null)
      setError(describeStaffError(err).message)
    } finally {
      if (!signal?.aborted && mounted.current) setLoading(false)
    }
  }, [action, page])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const rows = data?.results ?? []
  const total = data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(total / STAFF_PAGE_SIZE))
  const btn =
    'cursor-pointer rounded-lg border border-cream-300 px-3 py-1.5 text-sm text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="mx-auto max-w-6xl" data-testid="staff-audit">
      <div className="mb-5">
        <h2 className="font-serif text-2xl text-ink">Audit log</h2>
        <p className="mt-1 text-sm text-muted">
          Staff actions and security events, newest first. Rows cannot be edited or deleted.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-72">
          <label htmlFor="audit-action" className="mb-1 block text-xs font-medium text-ink">Action</label>
          <select
            id="audit-action"
            value={action}
            onChange={(event) => { setAction(event.target.value); setPage(1) }}
            className={`${selectClass} w-full`}
          >
            {AUDIT_ACTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
        <p className="text-xs text-muted sm:ml-auto" aria-live="polite">
          {data && !error ? `${total} entr${total === 1 ? 'y' : 'ies'}` : ''}
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
          <Spinner size="md" /> Loading audit log…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-cream-300 px-6 py-14 text-center" data-testid="audit-empty">
          <p className="text-sm text-ink">{action ? 'No entries for this action.' : 'No entries yet.'}</p>
        </div>
      ) : (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
          <AuditTable rows={rows} />
          <AuditList rows={rows} />
          {pageCount > 1 && (
            <nav aria-label="Audit pages" className="mt-5 flex items-center justify-between gap-3">
              <button type="button" className={btn} disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>Previous</button>
              <span className="text-xs text-muted">Page {page} of {pageCount}</span>
              <button type="button" className={btn} disabled={page >= pageCount || loading} onClick={() => setPage((p) => p + 1)}>Next</button>
            </nav>
          )}
        </div>
      )}
    </div>
  )
}

export default function StaffAuditPage() {
  return (
    <StaffGate area="The audit log">
      <AuditPageBody />
    </StaffGate>
  )
}
