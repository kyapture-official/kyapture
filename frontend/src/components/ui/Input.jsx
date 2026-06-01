import React from 'react'

export default function Input({
  label,
  error,
  className = '',
  hint,
  ...props
}) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label className="text-sm font-medium text-ink/80">{label}</label>
      )}
      <input
        className={`
          w-full px-4 py-2.5 bg-white border rounded-lg text-sm text-ink
          placeholder:text-muted
          border-cream-300 focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200
          transition-all duration-150
          ${error ? 'border-red-400 focus:border-red-400 focus:ring-red-100' : ''}
          ${className}
        `}
        {...props}
      />
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
