// File Location: frontend/src/pages/subscription/BillingPage.jsx
// VERSION: Gold-Standard Production — Redesigned UI polish

import { useState, useEffect, useRef } from 'react'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import { useSubscription } from '../../hooks/useSubscription'
import { useToast } from '../../components/ui/Toast'
import { formatCurrency } from '../../utils/formatters'
import Spinner from '../../components/ui/Spinner'

const STATUS_BADGE_STYLES = {
  active:    'bg-emerald-50 text-emerald-800 border-emerald-200',
  pending:   'bg-amber-50 text-amber-800 border-amber-200',
  expired:   'bg-red-50 text-red-800 border-red-200',
  cancelled: 'bg-slate-100 text-muted border-slate-200',
}

export default function BillingPage() {
  const toast = useToast()
  const isMountedRef = useRef(false)
  const abortControllerRef = useRef(null)
  const receiptPreviewRef = useRef(null)

  const { subscription, plan: activePlan, refetch: refetchSubscription } = useSubscription()

  const [plans, setPlans] = useState([])
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)

  const [selectedPlan, setSelectedPlan] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [receiptPreview, setReceiptPreview] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [notes, setNotes] = useState('')

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
        const [plansData, paymentsData] = await Promise.all([
          subscriptionsApi.getPlans(controller.signal),
          subscriptionsApi.paymentHistory(controller.signal),
        ])

        if (isMountedRef.current) {
          const plansList = plansData.results || plansData || []
          setPlans(plansList)
          setPayments(paymentsData.results || paymentsData || [])

          const queryParams = new URLSearchParams(window.location.search)
          const targetPlanId = queryParams.get('plan_id')
          if (targetPlanId) {
            const match = plansList.find((p) => String(p.id) === String(targetPlanId))
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
    clearReceipt()
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > 5 * 1024 * 1024) {
      toast('Screenshot attachment must be under 5MB.', 'warning')
      return
    }

    if (receiptPreviewRef.current) {
      URL.revokeObjectURL(receiptPreviewRef.current)
    }

    const previewUrl = URL.createObjectURL(file)
    receiptPreviewRef.current = previewUrl
    setReceipt(file)
    setReceiptPreview(previewUrl)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!selectedPlan || !receipt) {
      toast('Please select a plan and upload your receipt screenshot.', 'warning')
      return
    }

    setSubmitting(true)
    const loaderId = toast('Uploading transaction proof...', 'loading')

    const formData = new FormData()
    formData.append('plan', selectedPlan.id)
    formData.append('amount', selectedPlan.price)
    formData.append('payment_proof', receipt)
    if (notes.trim()) {
      formData.append('notes', notes.trim())
    }

    try {
      await subscriptionsApi.submitManualPayment(formData)

      toast.dismiss(loaderId)
      toast('Receipt uploaded successfully. Admin review in progress.', 'success')

      clearReceipt()
      setNotes('')

      const freshHistory = await subscriptionsApi.paymentHistory()
      if (isMountedRef.current) {
        setPayments(freshHistory.results || freshHistory || [])
      }
      refetchSubscription()
    } catch (err) {
      toast.dismiss(loaderId)
      const errorMsg = err.response?.data?.error || err.response?.data?.detail || 'Upload submission failed.'
      toast(errorMsg, 'error')
    } finally {
      if (isMountedRef.current) setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <Spinner size="lg" className="text-slate-400" />
      </div>
    )
  }

  const subStatus = subscription?.status || 'pending'

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-fade-up">
      {/* Header */}
      <header className="space-y-1">
        <h1 className="font-serif text-3xl md:text-4xl text-ink">Account Billing</h1>
        <p className="text-sm text-muted">Manage your subscription tier and upload payment receipt screenshots.</p>
      </header>

      {/* Subscription Status */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-card space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center">
            <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          </div>
          <h2 className="font-serif text-xl text-ink">Subscription Status</h2>
        </div>

        {activePlan ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-light">
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Active Tier</span>
              <span className="font-semibold text-ink text-sm">{activePlan.name}</span>
            </div>
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Expires On</span>
              <span className="font-semibold text-ink text-sm">
                {subscription?.expires_at ? new Date(subscription.expires_at).toLocaleDateString() : 'Never'}
              </span>
            </div>
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider mb-1">Verification Status</span>
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border uppercase mt-0.5 ${
                STATUS_BADGE_STYLES[subStatus] || STATUS_BADGE_STYLES.pending
              }`}>
                {subStatus}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted font-light leading-relaxed">
            You are currently running on the Free tier plan. Select a tier below to request an upgrade.
          </p>
        )}
      </section>

      {/* Pricing Selector */}
      <section className="space-y-6">
        <h2 className="font-serif text-2xl text-ink">1. Choose Upgrade Tier</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {plans.map((p) => {
            const isSelected = selectedPlan?.id === p.id
            const isActive = activePlan?.id === p.id

            return (
              <div
                key={p.id}
                onClick={() => !isActive && handleSelectPlan(p)}
                role="button"
                tabIndex={isActive ? -1 : 0}
                onKeyDown={(e) => {
                  if (!isActive && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    handleSelectPlan(p)
                  }
                }}
                className={`p-6 rounded-2xl border transition-all duration-300 cursor-pointer ${
                  isActive
                    ? 'border-slate-200 bg-slate-50/40 opacity-70 cursor-not-allowed select-none'
                    : isSelected
                    ? 'border-teal-500 bg-white shadow-card-hover scale-[1.02]'
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-card'
                }`}
              >
                <h3 className="font-serif text-lg text-ink font-medium">{p.name}</h3>
                <p className="text-2xl font-bold text-ink mt-1">{formatCurrency(p.price)}</p>
                {isActive && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-50 text-emerald-600 uppercase tracking-widest mt-3">
                    Active Plan
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {selectedPlan && (
          <form onSubmit={handleSubmit} className="space-y-6 p-6 border border-slate-200 rounded-2xl bg-white shadow-card animate-fade-up">
            <h3 className="font-serif text-xl text-ink">2. Upload Proof of Transfer</h3>
            <p className="text-xs text-slate-500 leading-relaxed max-w-2xl font-light">
              Transfer <span className="font-bold text-ink">{formatCurrency(selectedPlan.price)}</span> to our standard eSewa account or bank portal. Take a screenshot confirmation and attach it below.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Screenshot Receipt</label>
                <div className="flex items-center gap-4">
                  <input
                    type="file"
                    accept="image/png, image/jpeg, image/webp"
                    onChange={handleFileChange}
                    className="hidden"
                    id="manual-receipt-input"
                    disabled={submitting}
                  />
                  <label
                    htmlFor="manual-receipt-input"
                    className="px-4 py-2 border border-slate-200 text-ink bg-white text-xs hover:bg-slate-50 transition-colors rounded-xl cursor-pointer font-medium"
                  >
                    Choose Image File
                  </label>
                  {receipt && <span className="text-xs text-ink truncate">{receipt.name}</span>}
                </div>
              </div>

              {receiptPreview && (
                <div className="relative border border-slate-200 rounded-xl max-w-[200px] h-32 overflow-hidden bg-slate-50">
                  <img src={receiptPreview} alt="Receipt preview" className="w-full h-full object-cover" />
                </div>
              )}

              <div>
                <label className="block text-[10px] uppercase font-bold text-ink tracking-wider mb-2">Notes (Optional)</label>
                <textarea
                  rows="3"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Enter transaction reference numbers or billing notes..."
                  className="w-full border border-slate-200 bg-white p-3 rounded-xl text-xs font-light text-ink focus:border-teal-500 focus:ring-0 outline-none transition-all"
                  disabled={submitting}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-teal-600 hover:bg-teal-700 text-white text-xs uppercase tracking-widest rounded-xl font-bold transition-all cursor-pointer disabled:opacity-50 shadow-sm hover:shadow-md"
            >
              {submitting ? 'Uploading Receipt...' : 'Submit Transaction Review'}
            </button>
          </form>
        )}
      </section>

      {/* Payment History */}
      <section className="space-y-4">
        <h2 className="font-serif text-2xl text-ink">Manual Transfer History</h2>
        {payments.length === 0 ? (
          <p className="text-xs text-muted font-light leading-relaxed py-4">No manual transfers submitted yet.</p>
        ) : (
          <div className="border border-slate-200 rounded-2xl overflow-hidden bg-white shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-light border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-500 font-medium uppercase text-[10px] tracking-wider">
                    <th className="p-4">Submission Date</th>
                    <th className="p-4">Upgrade Tier</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Notes</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Receipt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {payments.map((p) => (
                    <tr key={p.id} className="hover:bg-slate-50/50 text-ink transition-colors">
                      <td className="p-4">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="p-4 font-bold">{p.plan_name || 'Standard Tier'}</td>
                      <td className="p-4 font-semibold">{formatCurrency(p.amount)}</td>
                      <td className="p-4 text-slate-500 italic max-w-xs truncate">{p.notes || '---'}</td>
                      <td className="p-4">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase ${
                          p.status === 'approved'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : p.status === 'rejected'
                            ? 'bg-red-50 text-red-800 border-red-200'
                            : 'bg-amber-50 text-amber-800 border-amber-200'
                        }`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="p-4">
                        {p.payment_proof ? (
                          <a
                            href={p.payment_proof}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-teal-600 underline underline-offset-2 hover:text-teal-700 transition-colors"
                          >
                            View
                          </a>
                        ) : (
                          <span className="text-muted">---</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
