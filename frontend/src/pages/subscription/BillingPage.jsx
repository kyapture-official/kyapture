// File Location: frontend/src/pages/subscription/BillingPage.jsx
// VERSION: Gold-Standard Production — Week 11
// Eliminates search-param render loops, fixes flat backend dictionary keys, and terminates memory leaks.

import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import { useSubscription } from '../../hooks/useSubscription'
import { useToast } from '../../components/ui/Toast'
import { formatCurrency } from '../../utils/formatters'
import Spinner from '../../components/ui/Spinner'

// Mapped against SubscriptionStatus.TextChoices (backend models.py) [weekly tasks.txt]
const STATUS_BADGE_STYLES = {
  active:    'bg-emerald-50 text-emerald-800 border-emerald-200',
  pending:   'bg-amber-50 text-amber-800 border-amber-200',
  expired:   'bg-red-50 text-red-800 border-red-200',
  cancelled: 'bg-cream-100 text-[#8C847A] border-cream-300',
}

export default function BillingPage() {
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const isMountedRef = useRef(false)
  const abortControllerRef = useRef(null)
  const receiptPreviewRef = useRef(null) // Tracks preview blob URLs to prevent memory leaks

  const { subscription, plan: activePlan, refetch: refetchSubscription } = useSubscription()

  // Grid list states
  const [plans, setPlans] = useState([])
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)

  // Form Submission States
  const [selectedPlan, setSelectedPlan] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [receiptPreview, setReceiptPreview] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [notes, setNotes] = useState('')

  // ── 1. Page Lifecycle Tracking ─────────────────────────────────────────────
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      abortControllerRef.current?.abort()
      
      // BUG RESOLUTION: Deallocate active preview blob URLs on unmount to prevent browser memory leaks
      if (receiptPreviewRef.current) {
        URL.revokeObjectURL(receiptPreviewRef.current)
      }
    }
  }, [])

  // ── 2. INITIAL METADATA LOADING ───────────────────────────────────────────
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

          // BUG RESOLUTION: Read parameter handshake once inside mounting effect.
          // By extracting query params here, we completely decouple this effect from
          // the reactive searchParams hook, eliminating parallel render-loop network storms.
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
  }, [toast]) // Safely removed searchParams to prevent rendering fetch-loops!

  // ── 3. STATE AND FILE RESETS ───────────────────────────────────────────────
  const clearReceipt = () => {
    if (receiptPreviewRef.current) {
      URL.revokeObjectURL(receiptPreviewRef.current)
      receiptPreviewRef.current = null
    }
    setReceipt(null)
    setReceiptPreview(null)
  }

  // BUG RESOLUTION: Explicitly clear the receipt when switching plans.
  // This prevents photographers from accidentally submitting receipts for incorrect pricing tiers.
  const handleSelectPlan = (p) => {
    setSelectedPlan(p)
    clearReceipt()
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Limit files to 5MB to match server payload capacity controls
    if (file.size > 5 * 1024 * 1024) {
      toast('Screenshot attachment must be under 5MB.', 'warning')
      return
    }

    // Revoke any previous preview before creating a new one to prevent memory leaks
    if (receiptPreviewRef.current) {
      URL.revokeObjectURL(receiptPreviewRef.current)
    }

    const previewUrl = URL.createObjectURL(file)
    receiptPreviewRef.current = previewUrl
    setReceipt(file)
    setReceiptPreview(previewUrl)
  }

  // ── 4. MANUAL PAYMENT SUBMISSION ───────────────────────────────────────────
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

      // Refresh local transfer history
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
        <Spinner size="lg" className="text-[#2C2825]" />
      </div>
    )
  }

  const subStatus = subscription?.status || 'pending'

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 text-[#2C2825] font-sans animate-fadeUp">
      <header className="space-y-1">
        <h1 className="font-serif text-3xl sm:text-4xl text-ink">Account Billing</h1>
        <p className="text-xs text-muted">Manage your subscription tier and upload payment receipt screenshots [weekly tasks.txt].</p>
      </header>

      {/* Subscription Status Details card */}
      <section className="bg-white border border-[#F4E8CC] rounded-3xl p-6 space-y-4">
        <h2 className="font-serif text-xl text-ink">Subscription Status</h2>

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
              {/* BUG RESOLUTION: Dynamically evaluate colors using STATUS_BADGE_STYLES mapping */}
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase mt-0.5 ${
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

      {/* Pricing selector card */}
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
                className={`p-6 rounded-2xl border transition-all duration-300 ${
                  isActive
                    ? 'border-[#E8DECE] bg-[#FDFAF5]/40 opacity-70 cursor-not-allowed select-none'
                    : isSelected
                    ? 'border-[#2C2825] bg-white shadow-lg scale-[1.02] cursor-pointer'
                    : 'border-[#F4E8CC] bg-white hover:border-[#E8DECE] cursor-pointer'
                }`}
              >
                <h3 className="font-serif text-lg text-ink font-medium">{p.name}</h3>
                <p className="text-2xl font-bold text-ink mt-1">{formatCurrency(p.price)}</p>
                {isActive && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-100 text-emerald-800 uppercase tracking-widest mt-3">
                    Active Plan
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {selectedPlan && (
          <form onSubmit={handleSubmit} className="space-y-6 p-6 border border-[#F4E8CC] rounded-3xl bg-white animate-fadeUp">
            <h3 className="font-serif text-xl text-ink">2. Upload Proof of Transfer</h3>
            <p className="text-xs text-muted leading-relaxed max-w-2xl font-light">
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
                    className="px-4 py-2 border border-cream-300 text-ink bg-white text-xs hover:bg-cream-50 transition-colors rounded-lg cursor-pointer font-medium"
                  >
                    Choose Image File
                  </label>
                  {receipt && <span className="text-xs text-ink truncate">{receipt.name}</span>}
                </div>
              </div>

              {receiptPreview && (
                <div className="relative border border-[#F4E8CC] rounded-xl max-w-[200px] h-32 overflow-hidden bg-cream-50">
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
                  className="w-full border border-cream-300 bg-white p-3 rounded-lg text-xs font-light text-ink focus:border-ink focus:ring-0 outline-none"
                  disabled={submitting}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-ink hover:opacity-95 text-[#FDFAF5] text-xs uppercase tracking-widest rounded-lg font-bold transition-opacity cursor-pointer disabled:opacity-50"
            >
              {submitting ? 'Uploading Receipt...' : 'Submit Transaction Review'}
            </button>
          </form>
        )}
      </section>

      {/* Payment history list */}
      <section className="space-y-4">
        <h2 className="font-serif text-2xl text-ink">Manual Transfer History</h2>
        {payments.length === 0 ? (
          <p className="text-xs text-muted font-light leading-relaxed py-4">No manual transfers submitted yet.</p>
        ) : (
          <div className="border border-[#F4E8CC] rounded-3xl overflow-hidden bg-white">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-light border-collapse">
                <thead>
                  <tr className="border-b border-[#F4E8CC] bg-[#FDFAF5]/40 text-[#8C847A] font-medium uppercase text-[10px] tracking-wider">
                    <th className="p-4">Submission Date</th>
                    <th className="p-4">Upgrade Tier</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Notes</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Receipt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-cream-100">
                  {payments.map((p) => (
                    <tr key={p.id} className="hover:bg-[#FDFAF5]/10 text-ink">
                      <td className="p-4">{new Date(p.created_at).toLocaleDateString()}</td>
                      {/* BUG RESOLUTION: Render p.plan_name flat key directly to bypass dict lookup crash */}
                      <td className="p-4 font-bold">{p.plan_name || 'Standard Tier'}</td>
                      <td className="p-4 font-semibold">{formatCurrency(p.amount)}</td>
                      <td className="p-4 text-[#8C847A] italic max-w-xs truncate">{p.notes || '—'}</td>
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
                      {/* BUG RESOLUTION: Restored p.payment_proof anchor tag viewing options */}
                      <td className="p-4">
                        {p.payment_proof ? (
                          <a
                            href={p.payment_proof}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-ink underline underline-offset-2 hover:text-[#8C6B35]"
                          >
                            View
                          </a>
                        ) : (
                          <span className="text-muted">—</span>
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