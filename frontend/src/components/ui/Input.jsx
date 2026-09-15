// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/ui/Input.jsx
import { useId, forwardRef } from 'react'

/**
 * WHAT: Standardized, fully accessible input primitive with ref forwarding.
 * WHY:  Forwards references to parent forms and validation engines, programmatically
 *       links labels via useId to prevent form conflicts, and exposes descriptive
 *       ARIA states to assist screen-reader navigation on error states.
 */
const Input = forwardRef(function Input(
  {
    label,
    error,
    hint,
    id: customId,
    className = '',
    type = 'text',
    ...props
  },
  ref,
) {
  const defaultId = useId()
  const id = customId || defaultId

  // Symmetrically map unique descriptor IDs for ARIA accessibility trees
  const errorId = error ? `${id}-error` : undefined
  const hintId  = hint  ? `${id}-hint`  : undefined

  // Space-separated list allows screen readers to read both errors and hints simultaneously
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  return (
    <div className="flex flex-col gap-1 w-full">
      {/* Label Linkage */}
      {label && (
        <label
          htmlFor={id}
          className="text-sm font-medium text-ink/80 cursor-pointer select-none"
        >
          {label}
        </label>
      )}

      <input
        {...props}
        ref={ref}
        id={id}
        type={type}
        // Emit aria-invalid only when invalid to prevent "invalid: no" announcements from screen readers
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={[
          'w-full px-4 py-2.5 bg-white border rounded-lg text-sm text-ink',
          'placeholder:text-slate-400 focus:outline-none transition-colors duration-150',
          // focus-visible restricts outline rings strictly to keyboard users.
          // ring-offset-1 creates an elegant, visible separation from the input border.
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
          error
            ? 'border-red-400 focus-visible:border-red-400 focus-visible:ring-red-400'
            : 'border-slate-200 focus-visible:border-teal-500 focus-visible:ring-teal-500',
          className,
        ].filter(Boolean).join(' ')}
      />

      {/* Hints & Errors Placement */}
      {hint && !error && (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      )}

      {error && (
        // role="alert" announces the error immediately when it appears after validation
        <p id={errorId} role="alert" className="text-xs text-red-500 font-medium">
          {error}
        </p>
      )}
    </div>
  )
})

Input.displayName = 'Input'

export default Input