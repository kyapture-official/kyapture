import { forwardRef } from 'react'

// All cream-*/ink tokens require tailwind.config.js to define them under theme.extend.colors.
// hover/active states on primary/outline use Tailwind's opacity modifier (bg-ink/80) so they
// always stay in the ink token's colour family regardless of what ink maps to.
const variants = {
  primary:   'bg-ink text-cream-50 hover:bg-ink/80 active:bg-ink/90',
  secondary: 'bg-cream-200 text-ink hover:bg-cream-300 border border-cream-300',
  ghost:     'text-ink hover:bg-cream-100',
  danger:    'bg-red-600 text-white hover:bg-red-700 active:bg-red-800',
  outline:   'border border-ink text-ink hover:bg-ink hover:text-cream-50',
}

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-7 py-3   text-base',
}

/**
 * WHAT: Standardized, Fully Accessible Button Primitive
 * WHY:  Enforces safe button types to prevent parent form hijacking on click,
 *       forwards references for focus and state managers, and handles polite
 *       screen-reader loading alerts symmetrically without losing accessible names [10].
 */
const Button = forwardRef(function Button(
  {
    children,
    type      = 'button',    // Safe default prevents parent form hijacking on click
    variant   = 'primary',
    size      = 'md',
    loading   = false,
    disabled  = false,
    className = '',
    ...props
  },
  ref,
) {
  const isDisabled = disabled || loading

  // Fragment return: the live region is a DOM sibling of the button, not a child.
  // JAWS silences aria-live regions that are inside interactive controls; placing
  // it outside guarantees announcements fire across all major screen readers [10].
  return (
    <>
      <button
        {...props}                        // Spread first — explicit props below always override
        ref={ref}                         // Ref targets the button element, not the Fragment
        type={type}
        disabled={isDisabled}
        aria-busy={loading || undefined}  // Omits attribute entirely when false
        className={[
          'inline-flex items-center justify-center gap-2',
          'font-sans font-medium rounded-lg whitespace-nowrap',
          'transition-colors duration-150 cursor-pointer', // prevents expensive reflow recalculations
          'disabled:opacity-50 disabled:cursor-not-allowed',
          // focus-visible restricts the ring to keyboard navigation only — not mouse clicks
          'focus-visible:outline-none',
          'focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-1',
          variants[variant] || variants.primary,  // Fallback guards invalid variant keys
          sizes[size]       || sizes.md,           // Fallback guards invalid size keys
          className,
        ].filter(Boolean).join(' ')} // Strips undefined/empty entries cleanly from DOM output
      >
        {loading && (
          // aria-hidden prevents the SVG path data from being read by screen readers
          <svg
            className="animate-spin h-4 w-4 shrink-0"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            {/* Standard, mathematically correct quarter-circle spinner path */}
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}

        {/* Wrapped in span so the accessible name is always derived from children,
            even when the live region sibling content changes */}
        <span>{children}</span>
      </button>

      {/* Live region: sibling to the button (not child) for cross-AT reliability.
          role="status" implies aria-live="polite" — no need to declare both.
          null on unload prevents a spurious blank announcement that aria-atomic
          would otherwise trigger when the empty-string change is detected. */}
      <span
        role="status"
        aria-atomic="true"
        className="sr-only"
      >
        {loading ? 'Processing, please wait…' : null}
      </span>
    </>
  )
})

Button.displayName = 'Button'

export default Button