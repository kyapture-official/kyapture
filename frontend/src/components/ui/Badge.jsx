const variants = {
  default: 'bg-cream-200 text-ink border border-cream-300',
  success: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
  warning: 'bg-amber-100 text-amber-700 border border-amber-200',
  danger:  'bg-red-100 text-red-600 border border-red-200',
  info:    'bg-sky-100 text-sky-700 border border-sky-200',
}

/**
 * WHAT: Standardized presentational badge tag.
 * WHY:  Renders metadata status indicators (published status, plan type, etc.)
 *       with clear visual states and a safe fallback for unrecognized variant keys.
 *
 * @param {object}  props
 * @param {*}       props.children        - Inner label content
 * @param {'default'|'success'|'warning'|'danger'|'info'} [props.variant='default']
 * @param {string}  [props.className='']  - Optional class overrides
 */
export default function Badge({ children, variant = 'default', className = '' }) {
  return (
    <span
      className={[
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        // Falls back to 'default' so an unrecognized variant never leaks
        // the string "undefined" into the DOM class list.
        variants[variant] || variants.default,
        className,
      ].filter(Boolean).join(' ')} // Strips all falsy values (null, undefined, empty strings)
    >
      {children}
    </span>
  )
}