// File Location: frontend/src/components/settings/SettingsUI.jsx
import { useId } from 'react'
import Spinner from '../ui/Spinner'

/** One titled settings card. `titleId` lets the section be a labelled landmark. */
export function Card({ title, description, children, className = '', headingLevel: H = 'h2' }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className={`rounded-2xl border border-cream-200 bg-surface-light p-5 shadow-card sm:p-6 ${className}`}>
      <header className="mb-5">
        <H id={id} className="font-serif text-xl text-ink">{title}</H>
        {description && <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>}
      </header>
      {children}
    </section>
  )
}

/**
 * An on/off control backed by a real checkbox (role=switch), so it works with a
 * keyboard and screen readers. `busy` disables it while a save is in flight.
 */
export function Switch({ checked, onChange, label, description, disabled = false, busy = false, id: customId }) {
  const generated = useId()
  const id = customId || generated
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-cream-200 bg-cream-100/60 p-4">
      <div className="min-w-0">
        <label htmlFor={id} className="block cursor-pointer text-sm font-medium text-ink">{label}</label>
        {description && <p id={`${id}-desc`} className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>}
      </div>
      <div className="flex flex-shrink-0 items-center gap-2 pt-0.5">
        {busy && <Spinner className="h-4 w-4" />}
        <label className="toggle-wrap">
          <input
            id={id}
            type="checkbox"
            role="switch"
            aria-checked={checked}
            aria-describedby={description ? `${id}-desc` : undefined}
            checked={checked}
            disabled={disabled || busy}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="toggle-slider" />
        </label>
      </div>
    </div>
  )
}

/** Inline result of the last save — shown only for a REAL outcome, never speculatively. */
export function InlineStatus({ status }) {
  if (!status?.message) return null
  const styles = status.kind === 'error'
    ? 'bg-red-50 text-red-700 border-red-100'
    : 'bg-brand-green-50 text-brand-green-800 border-brand-green-200'
  return (
    <p role={status.kind === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2 text-xs ${styles}`}>
      {status.message}
    </p>
  )
}

export function LoadingBlock({ label = 'Loading…' }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-3 py-14 text-sm text-muted">
      <Spinner className="h-5 w-5" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBlock({ message, onRetry }) {
  return (
    <div role="alert" className="rounded-xl border border-red-100 bg-red-50 p-5 text-center">
      <p className="text-sm text-red-700">{message || 'Something went wrong.'}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 cursor-pointer rounded-lg border border-red-200 bg-white px-4 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
        >
          Try again
        </button>
      )}
    </div>
  )
}

/** A read-only labelled value (used by Account / Privacy facts). */
export function ReadOnlyRow({ label, value, hint }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-cream-200 py-3 last:border-b-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
      <dt className="text-xs font-medium uppercase tracking-wider text-muted">{label}</dt>
      <dd className="min-w-0 text-sm text-ink sm:text-right">
        <span className="break-words">{value}</span>
        {hint && <span className="mt-0.5 block text-[11px] text-muted">{hint}</span>}
      </dd>
    </div>
  )
}
