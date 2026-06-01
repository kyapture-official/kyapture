import React, { useEffect, useState } from 'react'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import Button from '../../components/ui/Button'
import Badge from '../../components/ui/Badge'
import Modal from '../../components/ui/Modal'
import { useToast } from '../../components/ui/Toast'
import { formatCurrency, formatDate } from '../../utils/formatters'
import { PAYMENT_METHODS } from '../../utils/constants'

export default function BillingPage() {
  const toast = useToast()
  const [plans, setPlans] = useState([])
  const [sub, setSub] = useState(null)
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [payModal, setPayModal] = useState(null) // selected plan
  const [form, setForm] = useState({ payment_method: 'esewa', proof: null, notes: '' })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    Promise.all([
      subscriptionsApi.plans().then((r) => setPlans(r.data.results || r.data)),
      subscriptionsApi.mySubscription().then((r) => setSub(r.data)).catch(() => {}),
      subscriptionsApi.paymentHistory().then((r) => setPayments(r.data.results || r.data)).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  const handlePay = async (e) => {
    e.preventDefault()
    if (!form.proof) return toast('Please attach a payment proof screenshot.', 'error')
    setSubmitting(true)
    const fd = new FormData()
    fd.append('plan', payModal.id)
    fd.append('payment_method', form.payment_method)
    fd.append('payment_proof', form.proof)
    fd.append('amount', payModal.price)
    fd.append('notes', form.notes)
    try {
      await subscriptionsApi.submitPayment(fd)
      toast('Payment submitted! Admin will review shortly.', 'success')
      setPayModal(null)
    } catch {
      toast('Failed to submit payment.', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="mb-8 animate-fade-up">
        <h1 className="font-serif text-4xl text-ink mb-1">Billing</h1>
        <p className="text-sm text-muted">Manage your subscription plan.</p>
      </div>

      {/* Current subscription */}
      {sub && (
        <div className="mb-8 bg-white rounded-2xl border border-cream-200 p-6 animate-fade-up delay-100">
          <h2 className="font-serif text-xl text-ink mb-4">Current Plan</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-ink">{sub.plan?.name}</p>
              <p className="text-sm text-muted mt-1">
                {formatCurrency(sub.plan?.price)}/month · Expires {formatDate(sub.expires_at)}
              </p>
            </div>
            <Badge variant={sub.status === 'active' ? 'success' : sub.status === 'pending' ? 'warning' : 'danger'}>
              {sub.status}
            </Badge>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4 pt-4 border-t border-cream-100">
            {[
              { label: 'Galleries', value: sub.plan?.max_galleries },
              { label: 'Photos / Gallery', value: sub.plan?.max_photos_per_gallery },
              { label: 'Storage', value: `${sub.plan?.storage_gb} GB` },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <p className="font-serif text-2xl text-ink">{value}</p>
                <p className="text-xs text-muted">{label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Plans */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1,2,3].map(i => <div key={i} className="skeleton h-64 rounded-2xl" />)}
        </div>
      ) : (
        <div className="mb-8 animate-fade-up delay-200">
          <h2 className="font-serif text-2xl text-ink mb-4">Available Plans</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {plans.map((plan, i) => {
              const isCurrent = sub?.plan?.id === plan.id
              return (
                <div
                  key={plan.id}
                  className={`bg-white rounded-2xl border p-6 flex flex-col
                    ${isCurrent ? 'border-ink' : 'border-cream-200 hover:border-cream-400'}
                    transition-colors duration-200`}
                  style={{ animationDelay: `${i * 0.1}s` }}
                >
                  {isCurrent && (
                    <Badge variant="default" className="w-fit mb-3">Current</Badge>
                  )}
                  <h3 className="font-serif text-2xl text-ink mb-1">{plan.name}</h3>
                  <p className="text-3xl font-light text-ink mb-4">
                    {formatCurrency(plan.price)}<span className="text-sm text-muted">/mo</span>
                  </p>
                  <ul className="flex flex-col gap-2 text-sm text-muted mb-6 flex-1">
                    <li>✓ {plan.max_galleries} galleries</li>
                    <li>✓ {plan.max_photos_per_gallery} photos per gallery</li>
                    <li>✓ {plan.storage_gb} GB storage</li>
                  </ul>
                  <Button
                    variant={isCurrent ? 'secondary' : 'primary'}
                    disabled={isCurrent}
                    onClick={() => setPayModal(plan)}
                  >
                    {isCurrent ? 'Your plan' : 'Subscribe'}
                  </Button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Payment history */}
      {payments.length > 0 && (
        <div className="animate-fade-up delay-300">
          <h2 className="font-serif text-2xl text-ink mb-4">Payment History</h2>
          <div className="bg-white rounded-2xl border border-cream-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-100 text-xs text-muted">
                  <th className="text-left px-5 py-3 font-medium">Plan</th>
                  <th className="text-left px-5 py-3 font-medium">Amount</th>
                  <th className="text-left px-5 py-3 font-medium">Method</th>
                  <th className="text-left px-5 py-3 font-medium">Status</th>
                  <th className="text-left px-5 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id} className="border-b border-cream-50 last:border-0">
                    <td className="px-5 py-3 text-ink font-medium">{p.plan?.name}</td>
                    <td className="px-5 py-3 text-ink">{formatCurrency(p.amount)}</td>
                    <td className="px-5 py-3 text-muted capitalize">{p.payment_method}</td>
                    <td className="px-5 py-3">
                      <Badge variant={p.status === 'approved' ? 'success' : p.status === 'rejected' ? 'danger' : 'warning'}>
                        {p.status}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-muted">{formatDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Payment modal */}
      <Modal open={Boolean(payModal)} onClose={() => setPayModal(null)} title={`Subscribe to ${payModal?.name}`}>
        <form onSubmit={handlePay} className="flex flex-col gap-4">
          <div className="bg-cream-100 rounded-xl px-4 py-3">
            <p className="text-sm text-muted">Amount due:</p>
            <p className="font-serif text-2xl text-ink">{payModal && formatCurrency(payModal.price)}/month</p>
          </div>

          <div>
            <label className="text-sm font-medium text-ink/80 block mb-2">Payment Method</label>
            <select
              className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200"
              value={form.payment_method}
              onChange={(e) => setForm((f) => ({ ...f, payment_method: e.target.value }))}
            >
              {PAYMENT_METHODS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-ink/80 block mb-1">Payment Proof Screenshot</label>
            <input
              type="file"
              accept="image/*"
              required
              onChange={(e) => setForm((f) => ({ ...f, proof: e.target.files[0] }))}
              className="w-full text-sm text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-cream-200 file:text-ink hover:file:bg-cream-300 cursor-pointer"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-ink/80 block mb-1">Notes (optional)</label>
            <textarea
              className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm focus:outline-none focus:border-cream-500 resize-none"
              rows={2}
              placeholder="Transaction ID, additional info..."
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>

          <p className="text-xs text-muted bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
            Your payment will be reviewed by our team and activated within 24 hours.
          </p>

          <div className="flex gap-3">
            <Button type="button" variant="secondary" onClick={() => setPayModal(null)} className="flex-1">
              Cancel
            </Button>
            <Button type="submit" loading={submitting} className="flex-1">
              Submit Payment
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
