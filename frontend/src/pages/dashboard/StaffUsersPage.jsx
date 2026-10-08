// File Location: frontend/src/pages/dashboard/StaffUsersPage.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from '../../components/ui/Modal'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/Toast'
import StaffGate from '../../components/shared/StaffGate'
import { staffApi } from '../../api/staffApi'
import { usePlans } from '../../hooks/usePlans'
import {
  canChangeStatus,
  describeStaffError,
  looksLikeEmail,
  planOptions,
  reasonProblem,
  REASON_MAX,
  SORT_OPTIONS,
  STAFF_PAGE_SIZE,
  STATUS_OPTIONS,
  STORAGE_OPTIONS,
  statusLabel,
  storageSummary,
} from '../../utils/staffFlow'
import { formatDate, formatDateTime, timeAgo } from '../../utils/formatters'

const fieldClass =
  'w-full rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500'

const isCancelled = (err) => err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'

const EMPTY_FILTERS = { q: '', plan: '', status: '', storage: '', sort: 'joined', page: 1 }

/**
 * Everything that came from a user or a staff member (name, email, the suspension reason) is
 * rendered as React text children, which are always escaped. There is no dangerouslySetInnerHTML
 * and no innerHTML on this page.
 */
function StatusBadge({ status }) {
  const suspended = status === 'suspended'
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
        suspended ? 'border-red-200 bg-red-50 text-red-800' : 'border-brand-green-200 bg-brand-green-50 text-brand-green-800'
      }`}
    >
      {statusLabel(status)}
    </span>
  )
}

function StorageMeter({ row }) {
  const { percent, label, full } = storageSummary(row)
  return (
    <div className="min-w-[8rem]">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-cream-200" role="img" aria-label={`${percent}% of storage used`}>
        <div className={`h-full rounded-full ${full ? 'bg-red-500' : 'bg-brand-green-600'}`} style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  )
}

function RowAction({ row, onChange }) {
  if (!canChangeStatus(row)) return <span className="text-xs text-muted">Staff account</span>
  const suspended = row.status === 'suspended'
  return (
    <button
      type="button"
      onClick={() => onChange(suspended ? 'reactivate' : 'suspend', row)}
      className={`cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
        suspended
          ? 'border-cream-300 text-ink hover:bg-cream-100'
          : 'border-red-200 text-red-700 hover:bg-red-50'
      }`}
    >
      {suspended ? 'Reactivate' : 'Suspend'}
    </button>
  )
}

function Reason({ row }) {
  if (row.status !== 'suspended') return null
  return (
    <p className="mt-1 max-w-[16rem] break-words text-xs text-muted" data-testid="suspension-reason">
      {row.suspended_at ? `${formatDate(row.suspended_at)}: ` : ''}
      {row.suspension_reason || 'No reason recorded (switched off in the admin).'}
    </p>
  )
}

function Who({ row }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-medium text-ink">{row.name}</p>
      <p className="break-all text-xs text-muted">{row.email}</p>
    </div>
  )
}

function UsersTable({ rows, onChange }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm" data-testid="users-table">
        <thead>
          <tr className="border-b border-cream-200 text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-medium">User</th>
            <th className="py-2 pr-4 font-medium">Plan</th>
            <th className="py-2 pr-4 font-medium">Storage</th>
            <th className="py-2 pr-4 font-medium">Collections</th>
            <th className="py-2 pr-4 font-medium">Joined</th>
            <th className="py-2 pr-4 font-medium">Last login</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 font-medium"><span className="sr-only">Action</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-cream-100 align-top" data-testid="user-row">
              <td className="max-w-[14rem] py-3 pr-4"><Who row={row} /></td>
              <td className="py-3 pr-4 text-ink">{row.plan_name}</td>
              <td className="py-3 pr-4"><StorageMeter row={row} /></td>
              <td className="py-3 pr-4 tabular-nums text-ink">{row.collection_count}</td>
              <td className="whitespace-nowrap py-3 pr-4 text-muted">{formatDate(row.joined)}</td>
              <td className="whitespace-nowrap py-3 pr-4 text-muted" title={row.last_login ? formatDateTime(row.last_login) : ''}>
                {row.last_login ? timeAgo(row.last_login) : 'Never'}
              </td>
              <td className="py-3 pr-4"><StatusBadge status={row.status} /><Reason row={row} /></td>
              <td className="py-3 text-right"><RowAction row={row} onChange={onChange} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UsersList({ rows, onChange }) {
  return (
    <ul className="divide-y divide-cream-200 border-y border-cream-200 md:hidden" data-testid="users-list">
      {rows.map((row) => (
        <li key={row.id} className="space-y-3 py-4" data-testid="user-row">
          <div className="flex items-start justify-between gap-3">
            <Who row={row} />
            <StatusBadge status={row.status} />
          </div>
          <Reason row={row} />
          <StorageMeter row={row} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt className="text-muted">Plan</dt><dd className="text-right text-ink">{row.plan_name}</dd>
            <dt className="text-muted">Collections</dt><dd className="text-right tabular-nums text-ink">{row.collection_count}</dd>
            <dt className="text-muted">Joined</dt><dd className="text-right text-ink">{formatDate(row.joined)}</dd>
            <dt className="text-muted">Last login</dt><dd className="text-right text-ink">{row.last_login ? timeAgo(row.last_login) : 'Never'}</dd>
          </dl>
          <div className="flex justify-end"><RowAction row={row} onChange={onChange} /></div>
        </li>
      ))}
    </ul>
  )
}

function ChangeStatusModal({ change, onClose, onDone }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState('')
  const [serverError, setServerError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const suspend = change?.mode === 'suspend'
  const row = change?.row

  const submit = async (event) => {
    event.preventDefault()
    if (submitting) return
    const found = reasonProblem(reason)
    setProblem(found)
    if (found) return
    setSubmitting(true)
    setServerError('')
    try {
      const updated = await (suspend ? staffApi.suspend(row.id, reason) : staffApi.reactivate(row.id, reason))
      if (!mounted.current) return
      toast(suspend ? `${row.email} suspended` : `${row.email} reactivated`, 'success')
      onDone(updated)
    } catch (err) {
      if (!mounted.current) return
      setServerError(describeStaffError(err).message)
      setSubmitting(false)
    }
  }

  return (
    <Modal open={Boolean(change)} onClose={submitting ? () => {} : onClose} title={suspend ? 'Suspend account' : 'Reactivate account'}>
      {row && (
        <form onSubmit={submit} noValidate>
          <p className="break-all text-sm text-ink"><span className="font-medium">{row.email}</span></p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
            {suspend ? (
              <>
                <li>They are signed out at once and cannot log in.</li>
                <li>Their galleries stop being public and downloads stop. Nothing is deleted.</li>
                <li>Reactivating brings the galleries and downloads back.</li>
              </>
            ) : (
              <>
                <li>They can log in again (a fresh sign-in is needed).</li>
                <li>Their galleries and download links work again.</li>
              </>
            )}
          </ul>

          <label htmlFor="staff-reason" className="mt-4 block text-sm font-medium text-ink">Reason</label>
          <textarea
            id="staff-reason"
            value={reason}
            onChange={(event) => { setReason(event.target.value); if (problem) setProblem('') }}
            maxLength={REASON_MAX}
            rows={3}
            aria-invalid={Boolean(problem)}
            aria-describedby="staff-reason-help"
            className={`${fieldClass} mt-1 resize-none ${problem ? 'border-red-400' : ''}`}
          />
          <div id="staff-reason-help" className="mt-1 flex justify-between gap-3 text-xs">
            <span role={problem ? 'alert' : undefined} className={problem ? 'text-red-700' : 'text-muted'}>
              {problem || 'Plain text. It is recorded in the audit log.'}
            </span>
            <span className="tabular-nums text-muted">{reason.length}/{REASON_MAX}</span>
          </div>

          {serverError && <p role="alert" className="mt-3 text-sm text-red-700">{serverError}</p>}

          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>Cancel</Button>
            <Button type="submit" variant={suspend ? 'danger' : 'primary'} size="sm" loading={submitting}>
              {suspend ? 'Suspend account' : 'Reactivate account'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

function Pager({ page, pageCount, loading, onPage }) {
  if (pageCount <= 1) return null
  const btn =
    'cursor-pointer rounded-lg border border-cream-300 px-3 py-1.5 text-sm text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <nav aria-label="User pages" className="mt-5 flex items-center justify-between gap-3">
      <button type="button" className={btn} disabled={page <= 1 || loading} onClick={() => onPage(page - 1)}>Previous</button>
      <span className="text-xs text-muted">Page {page} of {pageCount}</span>
      <button type="button" className={btn} disabled={page >= pageCount || loading} onClick={() => onPage(page + 1)}>Next</button>
    </nav>
  )
}

function UsersPageBody() {
  const { plans } = usePlans()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [searchText, setSearchText] = useState('')
  const [searchError, setSearchError] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [change, setChange] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const result = await staffApi.users(filters, signal)
      if (signal?.aborted || !mounted.current) return
      setData(result)
    } catch (err) {
      if (isCancelled(err) || signal?.aborted || !mounted.current) return
      setData(null)
      setError(describeStaffError(err).message)
    } finally {
      if (!signal?.aborted && mounted.current) setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const setFilter = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value, page: 1 }))

  const search = (event) => {
    event.preventDefault()
    const text = searchText.trim()
    if (!text) { clearSearch(); return }
    if (!looksLikeEmail(text)) {
      setSearchError('Enter one complete email address, for example name@example.com.')
      return
    }
    setSearchError('')
    setFilters((current) => ({ ...current, q: text, page: 1 }))
  }

  const clearSearch = () => {
    setSearchText('')
    setSearchError('')
    setFilters((current) => ({ ...current, q: '', page: 1 }))
  }

  const finished = (updated) => {
    setChange(null)
    // A row that no longer matches an active status filter leaves the list; otherwise it is updated in place.
    if (filters.status) { load(); return }
    setData((current) => current && ({
      ...current,
      results: current.results.map((row) => (row.id === updated.id ? updated : row)),
    }))
  }

  const rows = data?.results ?? []
  const total = data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(total / STAFF_PAGE_SIZE))
  const filtered = Boolean(filters.q || filters.plan || filters.status || filters.storage)

  return (
    <div className="mx-auto max-w-6xl" data-testid="staff-users">
      <div className="mb-5">
        <h2 className="font-serif text-2xl text-ink">Users</h2>
        <p className="mt-1 text-sm text-muted">
          Every account, newest first. Search finds one account by its full email address.
        </p>
      </div>

      <form onSubmit={search} noValidate className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start" role="search">
        <div className="flex-1">
          <label htmlFor="staff-search" className="sr-only">Find an account by email address</label>
          <input
            id="staff-search"
            type="email"
            inputMode="email"
            autoComplete="off"
            value={searchText}
            onChange={(event) => { setSearchText(event.target.value); if (searchError) setSearchError('') }}
            placeholder="Full email address, e.g. name@example.com"
            aria-invalid={Boolean(searchError)}
            aria-describedby={searchError ? 'staff-search-error' : undefined}
            className={`${fieldClass} ${searchError ? 'border-red-400' : ''}`}
          />
          {searchError && <p id="staff-search-error" role="alert" className="mt-1 text-xs text-red-700">{searchError}</p>}
        </div>
        <div className="flex gap-2">
          <Button type="submit" size="sm">Search</Button>
          {filters.q && <Button variant="ghost" size="sm" onClick={clearSearch}>Clear</Button>}
        </div>
      </form>

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['plan', 'Plan', planOptions(plans)],
          ['status', 'Status', STATUS_OPTIONS],
          ['storage', 'Storage', STORAGE_OPTIONS],
          ['sort', 'Sort by', SORT_OPTIONS],
        ].map(([key, label, options]) => (
          <div key={key}>
            <label htmlFor={`staff-${key}`} className="mb-1 block text-xs font-medium text-ink">{label}</label>
            <select id={`staff-${key}`} value={filters[key]} onChange={setFilter(key)} className={fieldClass}>
              {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        ))}
      </div>

      <p className="mb-3 text-xs text-muted" aria-live="polite">
        {data && !error ? `${total} account${total === 1 ? '' : 's'}${filtered ? ' match' : ''}` : ''}
      </p>

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
          <Spinner size="md" /> Loading users…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-cream-300 px-6 py-14 text-center" data-testid="users-empty">
          <p className="text-sm text-ink">{filtered ? 'No account matches.' : 'No accounts yet.'}</p>
          {filtered && <p className="mt-1 text-xs text-muted">Check the email address or clear a filter.</p>}
        </div>
      ) : (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
          <UsersTable rows={rows} onChange={(mode, row) => setChange({ mode, row })} />
          <UsersList rows={rows} onChange={(mode, row) => setChange({ mode, row })} />
          <Pager page={filters.page} pageCount={pageCount} loading={loading} onPage={(page) => setFilters((c) => ({ ...c, page }))} />
        </div>
      )}

      {change && <ChangeStatusModal key={`${change.mode}-${change.row.id}`} change={change} onClose={() => setChange(null)} onDone={finished} />}
    </div>
  )
}

export default function StaffUsersPage() {
  return (
    <StaffGate area="The user list">
      <UsersPageBody />
    </StaffGate>
  )
}
