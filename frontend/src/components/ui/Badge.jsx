import React from 'react'

const variants = {
  default:  'bg-cream-200 text-ink',
  success:  'bg-emerald-100 text-emerald-700',
  warning:  'bg-amber-100 text-amber-700',
  danger:   'bg-red-100 text-red-600',
  info:     'bg-sky-100 text-sky-700',
}

export default function Badge({ children, variant = 'default', className = '' }) {
  return (
    <span className={`
      inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
      ${variants[variant]} ${className}
    `}>
      {children}
    </span>
  )
}
