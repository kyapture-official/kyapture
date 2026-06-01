import React from 'react'

const variants = {
  primary:   'bg-ink text-cream-50 hover:bg-stone-700 active:bg-stone-950',
  secondary: 'bg-cream-200 text-ink hover:bg-cream-300 border border-cream-300',
  ghost:     'text-ink hover:bg-cream-100',
  danger:    'bg-red-600 text-white hover:bg-red-700',
  outline:   'border border-ink text-ink hover:bg-ink hover:text-cream-50',
}

const sizes = {
  sm:  'px-3 py-1.5 text-sm',
  md:  'px-5 py-2.5 text-sm',
  lg:  'px-7 py-3 text-base',
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  ...props
}) {
  return (
    <button
      disabled={disabled || loading}
      className={`
        inline-flex items-center justify-center gap-2 font-sans font-medium
        rounded-lg transition-all duration-150 cursor-pointer
        disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${sizes[size]} ${className}
      `}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
        </svg>
      )}
      {children}
    </button>
  )
}
