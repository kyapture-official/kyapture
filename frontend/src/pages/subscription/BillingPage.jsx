// File Location: frontend/src/pages/subscription/BillingPage.jsx
// VERSION: Gold-Standard Production — Redesigned UI polish
// 7.5-B: the payment instructions come from the admin-edited row, a payment needs a transaction ID and a proof
// (image or PDF), and the page shows the real review states (pending, rejected with its reason, active, lapsed).

import { useState, useEffect, useRef } from 'react'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import { galleriesApi } from '../../api/galleriesApi'
import { useSubscription } from '../../hooks/useSubscription'
import { useToast } from '../../components/ui/Toast'
import { formatCurrency, formatDate, formatPlanPrice } from '../../utils/formatters'
import {
  billingState,
  DEFAULT_PROOF_MAX_MB,
  describeSubmitError,
  livePlanOf,
  paymentDetail,
  PROOF_ACCEPT,
  proofProblem,
  REFERENCE_MAX,
  referenceProblem,
} from '../../utils/billingFlow'
import PlanComparisonTable from '../../components/billing/PlanComparisonTable'
import StorageMeter from '../../components/billing/StorageMeter'
import Spinner from '../../components/ui/Spinner'

const STATUS_BADGE_STYLES = {
  active:    'bg-brand-green-50 text-brand-green-800 border-brand-green-200',
  pending:   'bg-amber-50 text-amber-800 border-amber-200',
  expired:   'bg-red-50 text-red-800 border-red-200',
  cancelled: 'bg-cream-100 text-muted border-cream-200',
}

const PAYMENT_BADGE_STYLES = {
  approved: 'bg-brand-green-50 text-brand-green-800 border-brand-green-200',
  rejected: 'bg-red-50 text-red-800 border-red-200',
  pending:  'bg-amber-50 text-amber-800 border-amber-200',
}

const inputClass =
  'w-full border border-cream-200 bg-surface-light p-3 rounded-xl text-xs font-light text-ink focus:border-brand-green-500 focus:ring-0 outline-none transition-all'

/**
 * Where to send the money. Every value is the admin-edited row served by the API and is drawn as React text
 * (escaped); the QR is a normal public image URL. Nothing here is typed into the code.
 */
function PaymentInstructions({ info }) {
  const rows = [
    ['Account name', info.account_name],
    ['eSewa ID', info.esewa_id],
    ['Bank', info.bank_name],
    ['Account number', info.bank_account_number],
    ['Branch', info.bank_branch],
  ].filter(([, value]) => value)

  return (
    <div className="space-y-3" data-testid="payment-instructions">
      <p className="text-[10px] uppercase font-bold text-ink tracking-wider">Send your payment to</p>
      <div className="flex flex-col sm:flex-row gap-5 sm:items-start">
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-xs font-light">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="font-semibold text-ink break-all">{value}</dd>
            </div>
          ))}
        </dl>
        {info.qr_url && (
          <img
            src={info.qr_url}
            alt="Payment QR code"
            data-testid="payment-qr"
            className="h-36 w-36 shrink-0 rounded-xl border border-cream-200 bg-white object-contain p-1"
          />
        )}
      </div>
      {info.note && <p className="text-xs text-muted leading-relaxed font-light whitespace-pre-line">{info.note}</p>}
    </div>
  )
}

function PaymentStatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase ${
      PAYMENT_BADGE_STYLES[status] || PAYMENT_BADGE_STYLES.pending
    }`}>
      {status}
    </span>
  )
}

export default function BillingPage() {
  const toast = useToast()
  const isMountedRef = useRef(false)
  const abortControllerRef = useRef(null)
  const receiptPreviewRef = useRef(null)

  const { subscription, refetch: refetchSubscription } = useSubscription()

  const [plans, setPlans] = useState([])
  // The Free tier is a plan row too (for the comparison table) but cannot be bought.
  const paidPlans = plans.filter((p) => !p.is_free)
  const [payments, setPayments] = useState([])
  const [usage, setUsage] = useState(null)
  const [instructions, setInstructions] = useState(null)
  const [loading, setLoading] = useState(true)

  const [selectedPlan, setSelectedPlan] = useState(null)
  const [reference, setReference] = useState('')
  const [receipt, setReceipt] = useState(null)
  const [receiptPreview, setReceiptPreview] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [notes, setNotes] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState('')

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      abortControllerRef.current?.abort()
      if (receiptPreviewRef.current) {
        URL.revokeObjectURL(receiptPreviewRef.current)
      }
    }
  }, [])

  useEffect(() => {
    async function loadBillingMetadata() {
      abortControllerRef.current?.abort()
      const controller = new AbortController()
      abortControllerRef.current = controller

      setLoading(true)
      try {
        const [plansData, paymentsData, usageData, instructionsData] = await Promise.all([
          subscriptionsApi.getPlans(controller.signal),
          subscriptionsApi.paymentHistory(controller.signal),
          // Usage only adds the video-minutes line: the page works without it.
          galleriesApi.getDashboardStats().catch(() => null),
          // Without the instructions the page says so and keeps the form shut: it never invents bank details.
          subscriptionsApi.getPaymentInstructions(controller.signal).catch(() => null),
        ])

        if (isMountedRef.current) {
          const plansList = plansData.results || plansData || []
          setPlans(plansList)
          setPayments(paymentsData.results || paymentsData || [])
          setUsage(usageData)
          setInstructions(instructionsData)

          const queryParams = new URLSearchParams(window.location.search)
          const targetPlanId = queryParams.get('plan_id')
          if (targetPlanId) {
            const match = plansList.find((p) => String(p.id) === String(targetPlanId) && !p.is_free)
            if (match) setSelectedPlan(match)
          }
        }
      } catch (err) {
        if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return
        if (isMountedRef.current) {
          toast('Failed to load transaction data.', 'error')
        }
      } finally {
        if (isMountedRef.current) setLoading(false)
      }
    }

    loadBillingMetadata()
  }, [toast])

  const clearReceipt = () => {
    if (receiptPreviewRef.current) {
      URL.revokeObjectURL(receiptPreviewRef.current)
      receiptPreviewRef.current = null
    }
    setReceipt(null)
    setReceiptPreview(null)
  }

  const handleSelectPlan = (p) => {
    setSelectedPlan(p)
    setFieldErrors({})
    setFormError('')
    clearReceipt()
  }

  const proofMaxMb = instructions?.proof_max_mb || DEFAULT_PROOF_MAX_MB

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const problem = proofProblem(file, proofMaxMb)
    if (problem) {
      e.target.value = ''
      setFieldErrors((current) => ({ ...current, payment_proof: problem }))
      return
    }

    if (receiptPreviewRef.current) {
      URL.revokeObjectURL(receiptPreviewRef.current)
      receiptPreviewRef.current = null
    }

    setFieldErrors((current) => ({ ...current, payment_proof: undefined }))
    setFormError('')
    setReceipt(file)
    if (file.type.startsWith('image/')) {
      const previewUrl = URL.createObjectURL(file)
      receiptPreviewRef.current = previewUrl
      setReceiptPreview(previewUrl)
    } else {
      setReceiptPreview(null)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return

    const problems = {}
    if (!selectedPlan) problems.plan = 'Choose a plan first.'
    const referenceIssue = referenceProblem(reference)
    if (referenceIssue) problems.reference = referenceIssue
    // A file the picker already refused keeps its own message instead of the generic "choose a file".
    const proofIssue = receipt ? proofProblem(receipt, proofMaxMb) : (fieldErrors.payment_proof || proofProblem(null))
    if (proofIssue) problems.payment_proof = proofIssue
    setFieldErrors(problems)
    setFormError(problems.plan || '')
    if (Object.keys(problems).length) return

    setSubmitting(true)
    const loaderId = toast('Uploading transaction proof...', 'loading')

    const formData = new FormData()
    formData.append('plan', selectedPlan.id)
    formData.append('amount', selectedPlan.price)
    formData.append('reference', reference.trim())
    formData.append('payment_proof', receipt)
    if (notes.trim()) {
      formData.append('notes', notes.trim())
    }

    try {
      const result = await subscriptionsApi.submitManualPayment(formData)

      toast.dismiss(loaderId)
      toast(result?.message || 'Payment submitted. We will review it shortly.', 'success')

      clearReceipt()
      setReference('')
      setNotes('')
      setFieldErrors({})
      setFormError('')

      const freshHistory = await subscriptionsApi.paymentHistory()
      if (isMountedRef.current) {
        setPayments(freshHistory.results || freshHistory || [])
      }
      refetchSubscription()
    } catch (err) {
      toast.dismiss(loaderId)
      const described = describeSubmitError(err)
      if (isMountedRef.current) {
        setFieldErrors(described.fieldErrors)
        setFormError(described.message)
      }
      toast(described.message, 'error')
    } finally {
      if (isMountedRef.current) setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <Spinner size="lg" className="text-muted" />
      </div>
    )
  }

  const state = billingState({ subscription, payments })
  // Only a live paid plan counts as the active tier; a lapsed one is Free (the server decides the same way).
  const activePlan = livePlanOf(subscription)
  const lapsedPlan = state.kind === 'lapsed' ? subscription?.plan : null
  const subStatus = subscription?.status || 'pending'
  const hasDetails = Boolean(
    instructions && (instructions.account_name || instructions.esewa_id || instructions.bank_name
      || instructions.bank_account_number || instructions.qr_url),
  )
  const periodDays = instructions?.period_days
  const renewing = Boolean(selectedPlan && activePlan && selectedPlan.id === activePlan.id)

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-fade-up">
      {/* Header */}
      <header className="space-y-1">
        <h1 className="font-serif text-3xl md:text-4xl text-ink">Account Billing</h1>
        <p className="text-sm text-muted">Manage your subscription tier and upload payment receipt screenshots.</p>
      </header>

      {/* Subscription Status */}
      <section className="bg-surface-light border border-cream-200 rounded-2xl p-6 shadow-card space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-brand-green-50 flex items-center justify-center">
            <svg className="w-5 h-5 text-brand-green-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          </div>
          <h2 className="font-serif text-xl text-ink">Subscription Status</h2>
        </div>

        {activePlan ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-light">
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Active Tier</span>
              <span className="font-semibold text-ink text-sm" data-testid="billing-active-plan">{activePlan.name}</span>
            </div>
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Expires On</span>
              <span className="font-semibold text-ink text-sm">
                {subscription?.expires_at ? formatDate(subscription.expires_at) : 'Never'}
              </span>
            </div>
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Status</span>
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border uppercase mt-0.5 ${
                STATUS_BADGE_STYLES[subStatus] || STATUS_BADGE_STYLES.pending
              }`}>
                {subStatus}
              </span>
            </div>
          </div>
        ) : lapsedPlan ? (
          <p className="text-xs text-muted font-light leading-relaxed" data-testid="billing-lapsed">
            Your {lapsedPlan.name} plan ended on {formatDate(subscription.expires_at)}. You are on the Free plan now: your files
            are kept, and the Free limits apply. Choose a tier below to renew.
          </p>
        ) : (
          <p className="text-xs text-muted font-light leading-relaxed">
            You are currently running on the Free tier plan. Select a tier below to request an upgrade.
          </p>
        )}

        {state.pending.length > 0 && (
          <div role="status" data-testid="billing-pending" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 leading-relaxed">
            {state.pending.length === 1
              ? `Your ${state.pending[0].plan_name} payment is waiting for review.`
              : `${state.pending.length} payments are waiting for review.`}{' '}
            We will email you as soon as it is decided. Your plan changes only when it is approved.
          </div>
        )}

        {state.rejected && (
          <div role="alert" data-testid="billing-rejected" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-900 leading-relaxed">
            Your {state.rejected.plan_name} payment (transaction ID {state.rejected.reference || 'none'}) was not approved.
            {state.rejected.rejection_reason && (
              <> Reason: <span className="font-semibold break-words">{state.rejected.rejection_reason}</span>.</>
            )}{' '}
            Your plan has not changed. You can submit a new receipt below.
          </div>
        )}

        {/* Storage used / limit and its warning / over-limit state come from the usage endpoint. */}
        {usage && <StorageMeter usage={usage} />}

        {/* Only a plan with a video allowance (> 0 min, not unlimited) has minutes to count. */}
        {usage?.video_minutes_limit > 0 && (
          <div className="text-xs font-light" data-testid="video-minutes-used">
            <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Video Minutes</span>
            <span className="font-semibold text-ink text-sm">
              {usage.video_minutes_used} / {usage.video_minutes_limit} min
            </span>
          </div>
        )}
      </section>

      {/* Pricing Selector */}
      <section className="space-y-6">
        <h2 className="font-serif text-2xl text-ink">1. Choose Upgrade Tier</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {paidPlans.map((p) => {
            const isSelected = selectedPlan?.id === p.id
            const isActive = activePlan?.id === p.id

            return (
              <div
                key={p.id}
                onClick={() => handleSelectPlan(p)}
                role="button"
                tabIndex={0}
                aria-pressed={isSelected}
                data-testid={`plan-card-${p.key}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    handleSelectPlan(p)
                  }
                }}
                className={`p-6 rounded-2xl border transition-all duration-300 cursor-pointer ${
                  isSelected
                    ? 'border-brand-green-500 bg-surface-light shadow-card-hover scale-[1.02]'
                    : 'border-cream-200 bg-surface-light hover:border-cream-300 hover:shadow-card'
                }`}
              >
                <h3 className="font-serif text-lg text-ink font-medium">{p.name}</h3>
                <p className="text-2xl font-bold text-ink mt-1">{formatPlanPrice(p.price)}</p>
                {isActive && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-brand-green-50 text-brand-green-600 uppercase tracking-widest mt-3">
                    Active Plan · Renew
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {selectedPlan && (
          <form onSubmit={handleSubmit} noValidate className="space-y-6 p-6 border border-cream-200 rounded-2xl bg-surface-light shadow-card animate-fade-up" data-testid="payment-form">
            <h3 className="font-serif text-xl text-ink">2. Pay and Upload Proof</h3>
            <p className="text-xs text-muted leading-relaxed max-w-2xl font-light">
              Transfer <span className="font-bold text-ink">{formatCurrency(selectedPlan.price)}</span>{' '}
              {periodDays ? `for ${periodDays} days of` : 'for'} {selectedPlan.name}
              {renewing ? ', added to your current period' : ''}, then enter the transaction ID and attach a screenshot or PDF of the payment.
            </p>

            {hasDetails ? (
              <PaymentInstructions info={instructions} />
            ) : (
              <p role="alert" data-testid="payment-details-missing" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                Payment details have not been set up yet, so a payment cannot be submitted right now. Please try again later.
              </p>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="payment-reference" className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Transaction ID</label>
                <input
                  id="payment-reference"
                  type="text"
                  value={reference}
                  maxLength={REFERENCE_MAX}
                  autoComplete="off"
                  onChange={(e) => { setReference(e.target.value); setFieldErrors((c) => ({ ...c, reference: undefined })) }}
                  placeholder="The reference shown on your eSewa or bank receipt"
                  aria-invalid={Boolean(fieldErrors.reference)}
                  aria-describedby={fieldErrors.reference ? 'payment-reference-error' : undefined}
                  className={`${inputClass} ${fieldErrors.reference ? 'border-red-400' : ''}`}
                  disabled={submitting}
                />
                {fieldErrors.reference && (
                  <p id="payment-reference-error" role="alert" className="mt-1 text-xs text-red-700">{fieldErrors.reference}</p>
                )}
              </div>

              <div>
                <label className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Proof of payment</label>
                <div className="flex items-center gap-4">
                  <input
                    type="file"
                    accept={PROOF_ACCEPT}
                    onChange={handleFileChange}
                    className="hidden"
                    id="manual-receipt-input"
                    disabled={submitting}
                  />
                  <label
                    htmlFor="manual-receipt-input"
                    className="px-4 py-2 border border-cream-200 text-ink bg-surface-light text-xs hover:bg-cream-100 transition-colors rounded-xl cursor-pointer font-medium"
                  >
                    Choose Image or PDF
                  </label>
                  {receipt && <span className="text-xs text-ink truncate">{receipt.name}</span>}
                </div>
                <p className="mt-1 text-[11px] text-muted">PNG, JPEG, WEBP or PDF, up to {proofMaxMb} MB.</p>
                {fieldErrors.payment_proof && (
                  <p role="alert" className="mt-1 text-xs text-red-700">{fieldErrors.payment_proof}</p>
                )}
              </div>

              {receiptPreview && (
                <div className="relative border border-cream-200 rounded-xl max-w-[200px] h-32 overflow-hidden bg-cream-100">
                  <img src={receiptPreview} alt="Receipt preview" className="w-full h-full object-cover" />
                </div>
              )}

              <div>
                <label htmlFor="payment-notes" className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Notes (Optional)</label>
                <textarea
                  id="payment-notes"
                  rows="3"
                  value={notes}
                  maxLength={500}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Anything we should know about this payment..."
                  className={inputClass}
                  disabled={submitting}
                />
              </div>
            </div>

            {formError && (
              <p role="alert" data-testid="payment-form-error" className="text-xs text-red-700">{formError}</p>
            )}

            <button
              type="submit"
              disabled={submitting || !hasDetails}
              className="w-full py-3 bg-brand-green-600 hover:bg-brand-green-700 text-white text-xs uppercase tracking-widest rounded-xl font-bold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
            >
              {submitting ? 'Uploading Receipt...' : 'Submit Transaction Review'}
            </button>
          </form>
        )}
      </section>

      {/* Plan comparison — generated from the plan table */}
      <section className="space-y-4" aria-labelledby="compare-plans">
        <h2 id="compare-plans" className="font-serif text-2xl text-ink">Compare plans</h2>
        <PlanComparisonTable plans={plans} currentPlanId={activePlan?.id ?? plans.find((p) => p.is_free)?.id} />
      </section>

      {/* Payment History */}
      <section className="space-y-4">
        <h2 className="font-serif text-2xl text-ink">Manual Transfer History</h2>
        {payments.length === 0 ? (
          <p className="text-xs text-muted font-light leading-relaxed py-4">No manual transfers submitted yet.</p>
        ) : (
          <>
            <div className="hidden md:block border border-cream-200 rounded-2xl overflow-hidden bg-surface-light shadow-card">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-light border-collapse" data-testid="payments-history">
                  <thead>
                    <tr className="border-b border-cream-200 bg-cream-100 text-muted font-medium uppercase text-[10px] tracking-wider">
                      <th className="p-4">Submitted</th>
                      <th className="p-4">Upgrade Tier</th>
                      <th className="p-4">Amount</th>
                      <th className="p-4">Transaction ID</th>
                      <th className="p-4">Status</th>
                      <th className="p-4">Details</th>
                      <th className="p-4">Proof</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cream-200">
                    {payments.map((p) => (
                      <tr key={p.id} className="hover:bg-cream-100/50 text-ink transition-colors align-top" data-testid="payment-history-row">
                        <td className="p-4">{formatDate(p.created_at)}</td>
                        <td className="p-4 font-bold">{p.plan_name || 'Standard Tier'}</td>
                        <td className="p-4 font-semibold">{formatCurrency(p.amount)}</td>
                        <td className="p-4 font-mono break-all max-w-[10rem]">{p.reference || '---'}</td>
                        <td className="p-4"><PaymentStatusBadge status={p.status} /></td>
                        <td className="p-4 text-muted max-w-xs break-words" data-testid="payment-detail">{paymentDetail(p, formatDate)}</td>
                        <td className="p-4 text-muted">{p.has_proof ? 'Attached' : '---'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <ul className="md:hidden divide-y divide-cream-200 border border-cream-200 rounded-2xl bg-surface-light shadow-card" data-testid="payments-history-list">
              {payments.map((p) => (
                <li key={p.id} className="p-4 space-y-2 text-xs font-light text-ink" data-testid="payment-history-row">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold">{p.plan_name || 'Standard Tier'} · {formatCurrency(p.amount)}</p>
                      <p className="text-muted">{formatDate(p.created_at)}</p>
                    </div>
                    <PaymentStatusBadge status={p.status} />
                  </div>
                  <p className="font-mono break-all text-muted">ID {p.reference || '---'}</p>
                  <p className="text-muted break-words" data-testid="payment-detail">{paymentDetail(p, formatDate)}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  )
}
