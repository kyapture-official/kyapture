import React, { useEffect, useCallback } from 'react'

export default function PhotoLightbox({ photos, index, onClose, onChange }) {
  const photo = photos[index]

  const prev = useCallback(() => onChange(Math.max(0, index - 1)), [index, onChange])
  const next = useCallback(() => onChange(Math.min(photos.length - 1, index + 1)), [index, onChange, photos.length])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft')  prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, prev, next])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 animate-fade-in">
      {/* Close */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>

      {/* Prev */}
      {index > 0 && (
        <button
          onClick={prev}
          className="absolute left-4 p-3 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/>
          </svg>
        </button>
      )}

      {/* Image */}
      <img
        src={photo.image}
        alt={photo.title || photo.original_name}
        className="max-h-[90vh] max-w-[90vw] object-contain rounded-xl shadow-2xl"
      />

      {/* Next */}
      {index < photos.length - 1 && (
        <button
          onClick={next}
          className="absolute right-4 p-3 rounded-xl bg-white/10 text-white hover:bg-white/20 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
          </svg>
        </button>
      )}

      {/* Counter */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/60 text-sm">
        {index + 1} / {photos.length}
      </div>
    </div>
  )
}
