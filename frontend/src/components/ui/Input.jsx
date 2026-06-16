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
          'placeholder:text-muted focus:outline-none transition-colors duration-150',
          // focus-visible restricts outline rings strictly to keyboard users.
          // ring-offset-1 creates an elegant, visible separation from the input border.
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
          error
            ? 'border-red-400 focus-visible:border-red-400 focus-visible:ring-red-400'
            // Brand Alignment: We use "ring-ink" instead of "ring-blue-500" to maintain Kyapture's
            // minimal luxury palette, while still easily satisfying the WCAG 3:1 contrast minimum.
            : 'border-cream-300 focus-visible:border-ink focus-visible:ring-ink',
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