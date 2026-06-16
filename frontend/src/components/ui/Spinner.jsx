const sizes = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-10 w-10',
}

/**
 * WHAT: Standardized, fully accessible loading spinner icon
 * WHY:  Renders a mathematically correct circular arc, suppresses screen-reader
 *       announcements via aria-hidden, and inherits the parent element's text color
 *       so contrast is always controlled at the call site, not hardcoded here.
 *
 * Usage:
 *   <Spinner />                          — md, inherits parent color
 *   <Spinner size="lg" className="text-blue-500" />
 *
 * Size fallback: invalid `size` prop silently falls back to 'md' rather than
 * appending the literal string "undefined" to the className.
 */
export default function Spinner({ size = 'md', className = '' }) {
  const sizeClass = sizes[size] || sizes.md

  return (
    <svg
      className={[
        'animate-spin shrink-0',
        // Inherits the parent element's text color. Set color on the parent
        // (e.g. <Spinner className="text-blue-600" />) to control contrast.
        'text-current',
        sizeClass,
        className,
      ].filter(Boolean).join(' ')}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      {/* Background track ring */}
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
      />

      {/* Active arc wedge — curved quarter-circle perimeter, not a pie-slice to center */}
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}