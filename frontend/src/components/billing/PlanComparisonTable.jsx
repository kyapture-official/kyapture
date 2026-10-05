// File Location: frontend/src/components/billing/PlanComparisonTable.jsx
import { formatPlanPrice } from '../../utils/formatters'
import { formatCollections, formatPhotoEstimate, formatStorage, formatVideoMinutes } from '../../utils/planLimits'

// Rows are generated from the plans API (the plan table): limits come from the
// plan's own fields, feature rows from each plan's `features` list. Nothing
// here names a plan, price or feature.

function Mark({ on, label }) {
  return on ? (
    <svg className="mx-auto h-4 w-4 text-brand-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} role="img" aria-label={`${label}: included`}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  ) : (
    <span className="text-muted" role="img" aria-label={`${label}: not included`}>—</span>
  )
}

export default function PlanComparisonTable({ plans, currentPlanId }) {
  if (!plans.length) return null

  // The photo estimate and the average photo size behind it come from the API.
  const averageMb = plans.find((p) => p.average_photo_size_mb != null)?.average_photo_size_mb
  const limitRows = [
    {
      key: 'storage',
      label: 'Photo storage',
      cell: (p) => (
        <>
          {formatStorage(p.storage_gb)}
          {formatPhotoEstimate(p) && (
            <span className="mt-0.5 block whitespace-nowrap text-[11px] text-muted" data-testid="photo-estimate">{formatPhotoEstimate(p)}</span>
          )}
        </>
      ),
    },
    { key: 'collections', label: 'Collections', cell: (p) => formatCollections(p.max_collections) },
    // Always shown: 0 = no video, empty = unlimited, N = N minutes.
    { key: 'video', label: 'Video', cell: (p) => formatVideoMinutes(p.video_minutes) },
  ]
  const featureRows = plans[0].features || []

  return (
    <div className="overflow-x-auto" data-testid="plan-comparison">
      <table className="w-full min-w-[34rem] border-collapse text-left text-xs">
        <caption className="sr-only">Compare plans</caption>
        <thead>
          <tr className="border-b border-cream-200">
            <th scope="col" className="w-2/5 py-3 pr-4 font-normal text-muted"><span className="sr-only">Feature</span></th>
            {plans.map((p) => (
              <th key={p.id} scope="col" className="px-2 py-3 text-center align-top">
                <span className="block font-serif text-base font-medium text-ink">{p.name}</span>
                <span className="block whitespace-nowrap text-[11px] font-normal text-muted">{formatPlanPrice(p.price)}</span>
                {p.id === currentPlanId && (
                  <span className="mt-1 inline-block rounded-full bg-brand-green-50 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-brand-green-700">Current</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-cream-200">
          {limitRows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="py-3 pr-4 font-normal text-ink">{row.label}</th>
              {plans.map((p) => <td key={p.id} className="px-2 py-3 text-center text-ink">{row.cell(p)}</td>)}
            </tr>
          ))}
          {featureRows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="py-3 pr-4 font-normal text-ink">{row.label}</th>
              {plans.map((p) => {
                const on = p.features?.find((f) => f.key === row.key)?.included
                return <td key={p.id} className="px-2 py-3 text-center"><Mark on={Boolean(on)} label={row.label} /></td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {averageMb != null && (
        <p className="mt-3 text-[11px] text-muted" data-testid="photo-estimate-note">
          Photo counts are estimates, based on an average photo of {averageMb} MB.
        </p>
      )}
    </div>
  )
}
