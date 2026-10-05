// File Location: frontend/src/components/billing/StorageMeter.jsx
import { Link } from 'react-router-dom'
import { formatBytes } from '../../utils/formatters'
import { formatStorageUsage } from '../../utils/planLimits'

const BAR = { ok: 'bg-brand-green-600', warning: 'bg-amber-500', full: 'bg-red-500', over: 'bg-red-500' }
const TEXT = { warning: 'text-amber-800', full: 'text-red-700', over: 'text-red-700' }

const NOTE = {
  warning: () => 'You are close to your storage limit.',
  full: () => 'Your storage is full. New uploads are paused until you delete files or upgrade.',
  over: (usage) =>
    `You are ${formatBytes(usage.storage_used_bytes - usage.plan_storage_limit_bytes)} over your plan's storage. ` +
    'Nothing was deleted: you can still view, download and delete files, but new uploads are paused.',
}

/**
 * Storage used / limit, from the usage endpoint (GET galleries/dashboard/stats/).
 * The bar colour and the note follow `storage_state`, which the backend decides
 * (ok / warning / full / over, threshold in one backend constant); this component
 * holds no limit and no threshold. A plan without a limit (staff) shows no bar.
 */
export default function StorageMeter({ usage, showUpgrade = false }) {
  const limited = usage.plan_storage_limit_bytes != null
  const state = usage.storage_state || 'ok'
  const percent = limited ? Math.min(100, usage.storage_percent_used ?? 0) : 0
  const note = NOTE[state]?.(usage)

  return (
    <div data-testid="storage-meter" data-state={state}>
      <div className="mb-1 flex justify-between gap-3 text-xs">
        <span className="text-ink/80">Storage</span>
        <span className="font-mono text-muted" data-testid="storage-meter-figures">
          {limited ? formatStorageUsage(usage) : `${formatBytes(usage.storage_used_bytes)} (no limit)`}
        </span>
      </div>
      {limited && (
        <div
          role="progressbar"
          aria-label="Storage"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percent)}
          className="h-1.5 overflow-hidden rounded-full bg-cream-200"
        >
          <div className={`h-full rounded-full ${BAR[state] || BAR.ok}`} style={{ width: `${percent}%` }} />
        </div>
      )}
      {note && (
        <p className={`mt-2 text-xs ${TEXT[state]}`} data-testid="storage-meter-note">
          {note}
          {showUpgrade && (
            <>
              {' '}
              <Link to="/dashboard/billing" className="font-medium underline underline-offset-2">Upgrade</Link>
            </>
          )}
        </p>
      )}
    </div>
  )
}
