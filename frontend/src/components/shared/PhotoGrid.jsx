import React, { useState } from 'react'
import PhotoLightbox from './PhotoLightbox'
import { formatBytes } from '../../utils/formatters'

export default function PhotoGrid({ photos = [], onDelete, showActions = false }) {
  const [lightbox, setLightbox] = useState(null)

  if (!photos.length) {
    return (
      <div className="py-20 flex flex-col items-center gap-3 text-muted">
        <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
        </svg>
        <p className="text-sm">No photos yet</p>
      </div>
    )
  }

  return (
    <>
      <div className="photo-grid">
        {photos.map((photo, idx) => (
          <div
            key={photo.id}
            className="photo-grid-item group relative overflow-hidden rounded-xl cursor-pointer"
            style={{ animationDelay: `${idx * 0.04}s` }}
            onClick={() => setLightbox(idx)}
          >
            <img
              src={photo.thumbnail || photo.image}
              alt={photo.title || photo.original_name}
              className="w-full h-auto block transition-transform duration-500 group-hover:scale-105"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-ink/0 group-hover:bg-ink/30 transition-all duration-300 rounded-xl" />
            {showActions && onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(photo.id) }}
                className="absolute top-2 right-2 p-1.5 rounded-lg bg-white/90 text-red-500
                           opacity-0 group-hover:opacity-100 transition-opacity duration-200
                           hover:bg-red-50"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            )}
            <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-ink/60 to-transparent
                            opacity-0 group-hover:opacity-100 transition-opacity duration-200 rounded-b-xl">
              <p className="text-white text-xs truncate">{photo.original_name}</p>
              <p className="text-white/60 text-xs">{formatBytes(photo.file_size)}</p>
            </div>
          </div>
        ))}
      </div>

      {lightbox !== null && (
        <PhotoLightbox
          photos={photos}
          index={lightbox}
          onClose={() => setLightbox(null)}
          onChange={setLightbox}
        />
      )}
    </>
  )
}
