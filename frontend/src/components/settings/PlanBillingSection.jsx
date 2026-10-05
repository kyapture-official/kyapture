// File Location: frontend/src/components/settings/PlanBillingSection.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { galleriesApi } from '../../api/galleriesApi'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import StorageMeter from '../billing/StorageMeter'
import { useSubscription } from '../../hooks/useSubscription'
import { formatCurrency, formatDate } from '../../utils/formatters'
import { Card, ErrorBlock, LoadingBlock, ReadOnlyRow } from './SettingsUI'

const BADGE = {
  active: 'bg-brand-green-50 text-brand-green-800 border-brand-green-200',
  pending: 'bg-amber-50 text-amber-800 border-amber-200',
  expired: 'bg-red-50 text-red-800 border-red-200',
  cancelled: 'bg-cream-100 text-muted border-cream-200',
  approved: 'bg-brand-green-50 text-brand-green-800 border-brand-green-200',
  rejected: 'bg-red-50 text-red-800 border-red-200',
  free: 'bg-cream-100 text-muted border-cream-200',
}

function Badge({ kind, children }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium capitalize ${BADGE[kind] || BADGE.free}`}>
      {children}
    </span>
  )
}

function Meter({ label, used, limit, unit = '' }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-ink/80">{label}</span>
        <span className="font-mono text-muted">
          {used}{unit} {limit ? `/ ${limit}${unit}` : '(no limit)'}
        </span>
      </div>
      {limit ? (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={Math.min(used, limit)}
          className="h-1.5 overflow-hidden rounded-full bg-cream-200"
        >
          <div className={`h-full rounded-full ${pct >= 90 ? 'bg-red-500' : 'bg-brand-green-600'}`} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  )
}

/**
 * Plan & Billing: a read-only summary of the REAL subscription, usage and
 * latest payment, built from the existing endpoints (my-subscription,
 * dashboard stats, payment history) — and a path into the existing Billing
 * page, which keeps every billing action (plans, upgrade, manual payment).
 * Nothing here duplicates that flow or invents a status.
 */
export default function PlanBillingSection() {
  const isMountedRef = useRef(true)
  const { subscription, plan, entitlements, loading: planLoading, error: planError, refetch } = useSubscription()
  const [stats, setStats] = useState(null)
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [usage, history] = await Promise.all([galleriesApi.getDashboardStats(), subscriptionsApi.paymentHistory()])
      if (!isMountedRef.current) return
      setStats(usage)
      setPayments(Array.isArray(history) ? history : [])
    } catch {
      if (isMountedRef.current) setError('Could not load your plan details.')
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading || planLoading) return <Card title="Plan & Billing"><LoadingBlock label="Loading your plan…" /></Card>
  if (error || planError || !stats) {
    return (
      <Card title="Plan & Billing">
        <ErrorBlock message={error || planError || 'Could not load your plan details.'} onRetry={() => { refetch(); load() }} />
      </Card>
    )
  }

  const status = subscription?.status
  const isPaid = Boolean(plan && status === 'active')
  const planName = isPaid ? plan.name : status === 'no_subscription' || !plan ? 'Free' : plan.name
  const badgeKind = isPaid ? 'active' : plan ? status || 'expired' : 'free'
  const badgeLabel = isPaid ? 'Active' : plan ? status || 'Inactive' : 'Free plan'
  const latestPayment = payments[0] || null

  return (
    <div className="space-y-6">
      <Card title="Current plan">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <p className="font-serif text-3xl text-ink">{planName}</p>
          <Badge kind={badgeKind}>{badgeLabel}</Badge>
        </div>
        <dl>
          {isPaid && (
            <ReadOnlyRow
              label="Renews / expires"
              value={subscription?.expires_at ? formatDate(subscription.expires_at) : '—'}
              hint={typeof subscription?.days_remaining === 'number' ? `${subscription.days_remaining} day(s) remaining` : undefined}
            />
          )}
          {plan && !isPaid && subscription?.expires_at && (
            <ReadOnlyRow label="Ended" value={formatDate(subscription.expires_at)} />
          )}
          <ReadOnlyRow
            label="Branding & watermark"
            value={entitlements.branding && entitlements.watermark ? 'Included' : 'Not included on this plan'}
          />
        </dl>
        <div className="mt-5 flex flex-wrap gap-2">
          <Link
            to="/dashboard/billing"
            className="inline-flex items-center rounded-lg bg-brand-green-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-1"
          >
            {isPaid ? 'Manage plan & billing' : 'View plans & upgrade'}
          </Link>
        </div>
      </Card>

      <Card title="Usage" description="Against your current plan's limits.">
        <div className="space-y-4">
          <Meter label="Collections" used={stats.galleries_used ?? 0} limit={stats.plan_gallery_limit} />
          <StorageMeter usage={stats} showUpgrade />
          {stats.video_minutes_limit > 0 && (
            <Meter label="Video" used={Number(stats.video_minutes_used ?? 0)} limit={stats.video_minutes_limit} unit=" min" />
          )}
          <p className="text-xs text-muted">
            {stats.photos_used ?? 0} photo{stats.photos_used === 1 ? '' : 's'} uploaded.
          </p>
        </div>
      </Card>

      <Card title="Billing status" description="Your most recent manual payment.">
        {latestPayment ? (
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div>
              <p className="text-ink">
                {latestPayment.plan_name} plan · {formatCurrency(latestPayment.amount)}
              </p>
              <p className="text-xs text-muted">Submitted {formatDate(latestPayment.created_at)}</p>
              {latestPayment.status === 'rejected' && latestPayment.notes && (
                <p className="mt-1 text-xs text-red-700">Note: {latestPayment.notes}</p>
              )}
            </div>
            <Badge kind={latestPayment.status}>{latestPayment.status}</Badge>
          </div>
        ) : (
          <p className="text-sm text-muted">You haven't submitted a payment yet.</p>
        )}
        <p className="mt-4 text-xs text-muted">
          Submit receipts and see your full payment history on the <Link to="/dashboard/billing" className="font-medium text-ink underline underline-offset-2">Billing page</Link>.
        </p>
      </Card>
    </div>
  )
}
