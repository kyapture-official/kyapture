// File Location: frontend/src/pages/dashboard/StaffPaymentsPage.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from '../../components/ui/Modal'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/Toast'
import StaffGate from '../../components/shared/StaffGate'
import { staffApi } from '../../api/staffApi'
import {
  canReviewPayment,
  describeStaffError,
  PAYMENT_STATUS_OPTIONS,
  paymentStatusLabel,
  proofIsImage,
  reasonProblem,
  REASON_MAX,
  STAFF_PAGE_SIZE,
} from '../../utils/staffFlow'
import { formatCurrency, formatDate, formatDateTime, timeAgo } from '../../utils/formatters'

const fieldClass =
  'w-full rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500'

const isCancelled = (err) => err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'

const BADGE = {
  pending: 'border-amber-200 bg-amber-50 text-amber-800',
  approved: 'border-brand-green-200 bg-brand-green-50 text-brand-green-800',
  rejected: 'border-red-200 bg-red-50 text-red-800',
}

/**
 * Everything that came from a user or a staff member (name, email, the transaction ID, the user's note,
 * a reject reason) is rendered as React text children, which are always escaped. There is no
 * dangerouslySetInnerHTML and no innerHTML on this page. The proof is shown only from a signed,
 * short-lived link the server minted for this staff member a moment ago; it is never stored here.
 */
function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[status] || BADGE.pending}`}>
      {paymentStatusLabel(status)}
    </span>
  )
}

function Who({ row }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-medium text-ink">{row.name}</p>
      <p className="break-all text-xs text-muted">{row.email}</p>
      <p className="mt-0.5 text-xs text-muted" title={formatDateTime(row.created_at)}>Submitted {timeAgo(row.created_at)}</p>
    </div>
  )
}

function Outcome({ row }) {
  if (row.status === 'pending') return null
  return (
    <p className="mt-1 max-w-[16rem] break-words text-xs text-muted" data-testid="payment-outcome">
      {row.reviewed_at ? `${formatDate(row.reviewed_at)}${row.reviewed_by ? ` by ${row.reviewed_by}` : ''}. ` : ''}
      {row.status === 'rejected' ? row.rejection_reason : row.period_end ? `Plan runs until ${formatDate(row.period_end)}.` : ''}
    </p>
  )
}

function RowActions({ row, onProof, onApprove, onReject }) {
  const reviewable = canReviewPayment(row)
  const button =
    'cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500'
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {row.has_proof && (
        <button type="button" onClick={() => onProof(row)} className={`${button} border-cream-300 text-ink hover:bg-cream-100`}>
          View proof
        </button>
      )}
      {row.status === 'pending' && !reviewable && <span className="text-xs text-muted">Your own payment</span>}
      {reviewable && (
        <>
          <button type="button" onClick={() => onReject(row)} className={`${button} border-red-200 text-red-700 hover:bg-red-50`}>
            Reject
          </button>
          <button type="button" onClick={() => onApprove(row)} className={`${button} border-brand-green-600 bg-brand-green-600 text-white hover:bg-brand-green-700`}>
            Approve
          </button>
        </>
      )}
    </div>
  )
}

function PaymentsTable({ rows, ...actions }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm" data-testid="payments-table">
        <thead>
          <tr className="border-b border-cream-200 text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-medium">User</th>
            <th className="py-2 pr-4 font-medium">Plan</th>
            <th className="py-2 pr-4 font-medium">Transaction ID</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 font-medium"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-cream-100 align-top" data-testid="payment-row">
              <td className="max-w-[16rem] py-3 pr-4"><Who row={row} /></td>
              <td className="py-3 pr-4">
                <p className="text-ink">{row.plan_name}</p>
                <p className="text-xs tabular-nums text-muted">{formatCurrency(row.amount)}</p>
                {row.current_plan_name && (
                  <p className="mt-1 max-w-[12rem] text-xs text-muted">
                    Now on {row.current_plan_name} until {formatDate(row.current_period_end)}
                  </p>
                )}
              </td>
              <td className="py-3 pr-4">
                <p className="break-all font-mono text-xs text-ink" data-testid="payment-reference">{row.reference || 'Not recorded'}</p>
                {row.notes && <p className="mt-1 max-w-[14rem] break-words text-xs text-muted">Note: {row.notes}</p>}
              </td>
              <td className="py-3 pr-4"><StatusBadge status={row.status} /><Outcome row={row} /></td>
              <td className="py-3"><RowActions row={row} {...actions} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PaymentsList({ rows, ...actions }) {
  return (
    <ul className="divide-y divide-cream-200 border-y border-cream-200 md:hidden" data-testid="payments-list">
      {rows.map((row) => (
        <li key={row.id} className="space-y-3 py-4" data-testid="payment-row">
          <div className="flex items-start justify-between gap-3">
            <Who row={row} />
            <StatusBadge status={row.status} />
          </div>
          <Outcome row={row} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt className="text-muted">Plan</dt><dd className="text-right text-ink">{row.plan_name}</dd>
            <dt className="text-muted">Amount</dt><dd className="text-right tabular-nums text-ink">{formatCurrency(row.amount)}</dd>
            <dt className="text-muted">Transaction ID</dt>
            <dd className="break-all text-right font-mono text-ink" data-testid="payment-reference">{row.reference || 'Not recorded'}</dd>
            {row.current_plan_name && (
              <>
                <dt className="text-muted">Now on</dt>
                <dd className="text-right text-ink">{row.current_plan_name} until {formatDate(row.current_period_end)}</dd>
              </>
            )}
          </dl>
          {row.notes && <p className="break-words text-xs text-muted">Note: {row.notes}</p>}
          <RowActions row={row} {...actions} />
        </li>
      ))}
    </ul>
  )
}

function ProofModal({ row, onClose }) {
  const [state, setState] = useState({ phase: 'loading', link: null, message: '' })
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const open = useCallback(async () => {
    setState({ phase: 'loading', link: null, message: '' })
    try {
      const link = await staffApi.paymentProofLink(row.id)
      if (mounted.current) setState({ phase: 'ready', link, message: '' })
    } catch (err) {
      if (mounted.current) setState({ phase: 'error', link: null, message: describeStaffError(err).message })
    }
  }, [row.id])

  useEffect(() => { open() }, [open])

  const image = proofIsImage(state.link?.content_type || row.proof_type)
  return (
    <Modal open onClose={onClose} title="Payment proof" size="lg">
      <p className="break-all text-xs text-muted">
        {row.email} · {row.plan_name} · {formatCurrency(row.amount)} · ID {row.reference || 'Not recorded'}
      </p>
      <div className="mt-3 min-h-[8rem]" data-testid="proof-body">
        {state.phase === 'loading' && (
          <div role="status" className="flex items-center justify-center gap-3 py-12 text-sm text-muted">
            <Spinner size="md" /> Opening the proof…
          </div>
        )}
        {state.phase === 'error' && (
          <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-5 text-center">
            <p className="text-sm text-red-800">{state.message}</p>
            <button type="button" onClick={open} className="mt-3 cursor-pointer rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-cream-100">
              Try again
            </button>
          </div>
        )}
        {state.phase === 'ready' && image && (
          <img
            src={state.link.url}
            alt="Payment proof"
            data-testid="proof-image"
            className="mx-auto max-h-[65vh] w-auto max-w-full rounded-lg border border-cream-200 object-contain"
            referrerPolicy="no-referrer"
            onError={() => setState({ phase: 'error', link: null, message: 'The proof could not be loaded. The link may have expired.' })}
          />
        )}
        {state.phase === 'ready' && !image && (
          <div className="rounded-xl border border-cream-200 px-4 py-8 text-center">
            <p className="text-sm text-ink">This proof is a PDF document.</p>
            <a
              href={state.link.url}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="proof-pdf-link"
              className="mt-3 inline-block rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2"
            >
              Open PDF
            </a>
          </div>
        )}
      </div>
      {state.phase === 'ready' && (
        <p className="mt-2 text-xs text-muted">
          This link works for {Math.round((state.link.expires_in || 0) / 60)} minutes and only for you. Opening it is recorded in the audit log.
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  )
}

function ReviewModal({ review, onClose, onDone }) {
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

  const approve = review.mode === 'approve'
  const row = review.row

  const submit = async (event) => {
    event.preventDefault()
    if (submitting) return
    if (!approve) {
      const found = reasonProblem(reason)
      setProblem(found)
      if (found) return
    }
    setSubmitting(true)
    setServerError('')
    try {
      const result = await (approve ? staffApi.approvePayment(row.id) : staffApi.rejectPayment(row.id, reason))
      if (!mounted.current) return
      if (result.changed) toast(approve ? `Approved ${row.email}'s ${row.plan_name} payment` : `Rejected ${row.email}'s payment`, 'success')
      else toast(result.message, 'info')
      onDone(result.payment)
    } catch (err) {
      if (!mounted.current) return
      const described = describeStaffError(err)
      setServerError(described.message)
      setSubmitting(false)
      // Someone else decided it first: the row is stale, so show what it is now.
      if (described.code === 'already_approved' || described.code === 'already_rejected') onDone(null)
    }
  }

  return (
    <Modal open onClose={submitting ? () => {} : onClose} title={approve ? 'Approve payment' : 'Reject payment'}>
      <form onSubmit={submit} noValidate>
        <p className="break-all text-sm text-ink">
          <span className="font-medium">{row.email}</span>: {row.plan_name}, {formatCurrency(row.amount)}
        </p>
        <p className="mt-1 break-all text-xs text-muted">Transaction ID {row.reference || 'Not recorded'}</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          {approve ? (
            <>
              <li>The {row.plan_name} plan unlocks for them at once.</li>
              <li>
                {row.current_plan_name === row.plan_name && row.current_period_end
                  ? `Their current period ends ${formatDate(row.current_period_end)}; this adds to it.`
                  : 'The paid period starts now.'}
              </li>
              <li>They are emailed. This is recorded in the audit log.</li>
            </>
          ) : (
            <>
              <li>Their plan does not change.</li>
              <li>They see your reason on the Billing page and are emailed it.</li>
            </>
          )}
        </ul>

        {!approve && (
          <>
            <label htmlFor="payment-reason" className="mt-4 block text-sm font-medium text-ink">Reason (shown to the user)</label>
            <textarea
              id="payment-reason"
              value={reason}
              onChange={(event) => { setReason(event.target.value); if (problem) setProblem('') }}
              maxLength={REASON_MAX}
              rows={3}
              aria-invalid={Boolean(problem)}
              aria-describedby="payment-reason-help"
              className={`${fieldClass} mt-1 resize-none ${problem ? 'border-red-400' : ''}`}
            />
            <div id="payment-reason-help" className="mt-1 flex justify-between gap-3 text-xs">
              <span role={problem ? 'alert' : undefined} className={problem ? 'text-red-700' : 'text-muted'}>
                {problem || 'Plain text, for example "The amount on the receipt is wrong".'}
              </span>
              <span className="tabular-nums text-muted">{reason.length}/{REASON_MAX}</span>
            </div>
          </>
        )}

        {serverError && <p role="alert" className="mt-3 text-sm text-red-700">{serverError}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button type="submit" variant={approve ? 'primary' : 'danger'} size="sm" loading={submitting}>
            {approve ? 'Approve payment' : 'Reject payment'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function Pager({ page, pageCount, loading, onPage }) {
  if (pageCount <= 1) return null
  const btn =
    'cursor-pointer rounded-lg border border-cream-300 px-3 py-1.5 text-sm text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <nav aria-label="Payment pages" className="mt-5 flex items-center justify-between gap-3">
      <button type="button" className={btn} disabled={page <= 1 || loading} onClick={() => onPage(page - 1)}>Previous</button>
      <span className="text-xs text-muted">Page {page} of {pageCount}</span>
      <button type="button" className={btn} disabled={page >= pageCount || loading} onClick={() => onPage(page + 1)}>Next</button>
    </nav>
  )
}

function PaymentsPageBody() {
  const [filters, setFilters] = useState({ status: 'pending', page: 1 })
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [proof, setProof] = useState(null)
  const [review, setReview] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const result = await staffApi.payments(filters, signal)
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

  const finished = (updated) => {
    setReview(null)
    // A decided payment leaves the pending list; in any other list it is updated in place.
    if (!updated || filters.status === 'pending') { load(); return }
    setData((current) => current && ({
      ...current,
      results: current.results.map((row) => (row.id === updated.id ? updated : row)),
    }))
  }

  const rows = data?.results ?? []
  const total = data?.count ?? 0
  const pageCount = Math.max(1, Math.ceil(total / STAFF_PAGE_SIZE))
  const actions = {
    onProof: setProof,
    onApprove: (row) => setReview({ mode: 'approve', row }),
    onReject: (row) => setReview({ mode: 'reject', row }),
  }

  return (
    <div className="mx-auto max-w-6xl" data-testid="staff-payments">
      <div className="mb-5">
        <h2 className="font-serif text-2xl text-ink">Payments</h2>
        <p className="mt-1 text-sm text-muted">
          Bank-transfer and eSewa payments waiting for a decision, oldest first. Approving unlocks the plan at once.
        </p>
      </div>

      <div className="mb-5 max-w-xs">
        <label htmlFor="payments-status" className="mb-1 block text-xs font-medium text-ink">Show</label>
        <select
          id="payments-status"
          value={filters.status}
          onChange={(event) => setFilters({ status: event.target.value, page: 1 })}
          className={fieldClass}
        >
          {PAYMENT_STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>

      <p className="mb-3 text-xs text-muted" aria-live="polite">
        {data && !error ? `${total} payment${total === 1 ? '' : 's'}` : ''}
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
          <Spinner size="md" /> Loading payments…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-cream-300 px-6 py-14 text-center" data-testid="payments-empty">
          <p className="text-sm text-ink">{filters.status === 'pending' ? 'No payments are waiting for review.' : 'No payments here.'}</p>
        </div>
      ) : (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
          <PaymentsTable rows={rows} {...actions} />
          <PaymentsList rows={rows} {...actions} />
          <Pager page={filters.page} pageCount={pageCount} loading={loading} onPage={(page) => setFilters((c) => ({ ...c, page }))} />
        </div>
      )}

      {proof && <ProofModal key={proof.id} row={proof} onClose={() => setProof(null)} />}
      {review && <ReviewModal key={`${review.mode}-${review.row.id}`} review={review} onClose={() => setReview(null)} onDone={finished} />}
    </div>
  )
}

export default function StaffPaymentsPage() {
  return (
    <StaffGate area="Payment review">
      <PaymentsPageBody />
    </StaffGate>
  )
}
