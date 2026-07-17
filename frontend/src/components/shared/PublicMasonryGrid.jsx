import React, { useState } from 'react'
import { useInView } from 'react-intersection-observer'

/**
 * Individual image renderer managing intersection observation,
 * aspect-ratio containment, state-synchronization, and asset-theft protection.
 */
function LazyPhoto({ photo, index, onPhotoClick }) {
  // Track the actual loaded image URI rather than boolean triggers to bypass post-paint rendering lag
  const [loadedSrc, setLoadedSrc] = useState(null)
  const [errorSrc,  setErrorSrc]  = useState(null)

  // Derived state calculations (evaluated synchronously during render execution)
  const isLoaded = loadedSrc === photo.image
  const hasError = errorSrc  === photo.image

  // Trigger loading 200px before the element enters the viewport to optimize perceived speed
  const { ref, inView } = useInView({
    triggerOnce: true,
    rootMargin: '200px 0px',
  })

  // Calculate strict CSS aspect ratio to reserve container space and prevent Cumulative Layout Shift (CLS)
  const aspectRatio =
    photo.width && photo.height ? `${photo.width} / ${photo.height}` : '3 / 2'

  /**
   * Prevents standard browser right-click context menus.
   * Mitigates casual image download theft for professional photographers.
   */
  const handleContextMenu = (e) => e.preventDefault()

  return (
    <div
      ref={ref}
      onClick={() => onPhotoClick?.(index)}
      className="group relative w-full overflow-hidden rounded-lg bg-cream-100 cursor-pointer mb-3 break-inside-avoid shadow-sm hover:shadow-md transition-shadow duration-300 select-none"
      style={{ aspectRatio }}
      onContextMenu={handleContextMenu}
    >
      {inView ? (
        <>
          {hasError ? (
            // Graceful error UI fallback with proper semantic icon
            <div className="absolute inset-0 bg-cream-200 flex flex-col items-center justify-center p-4">
              <svg
                className="w-5 h-5 text-cream-400 mb-1"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
                />
              </svg>
              <span className="text-cream-400 text-xs font-light select-none pointer-events-none">
                Unavailable
              </span>
            </div>
          ) : (
            <img
              src={photo.image}
              alt={photo.alt || photo.original_name || 'Gallery item'}
              loading="lazy"
              decoding="async"
              className={`
                w-full h-full object-cover pointer-events-none
                transition-[opacity,transform] duration-500 ease-out
                group-hover:scale-[1.03]
                ${isLoaded ? 'opacity-100' : 'opacity-0'}
              `}
              style={{
                WebkitTouchCallout: 'none',
                WebkitUserSelect: 'none',
              }}
              onLoad={() => setLoadedSrc(photo.image)}
              onError={() => setErrorSrc(photo.image)}
            />
          )}
          {/* Subtle hover overlay to enhance interactive feedback */}
          <div className="absolute inset-0 bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
        </>
      ) : (
        // Skeleton placeholder matching the exact aspect ratio of the incoming image
        <div className="w-full h-full bg-cream-100 animate-pulse" />
      )}
    </div>
  )
}

export default function PublicMasonryGrid({ photos, onPhotoClick }) {
  if (!photos || photos.length === 0) return null

  return (
    <div className="columns-2 sm:columns-3 lg:columns-4 xl:columns-5 gap-3 p-1 w-full mx-auto">
      {photos.map((photo, index) => (
        <LazyPhoto
          key={photo.id ?? index}
          photo={photo}
          index={index}
          onPhotoClick={onPhotoClick}
        />
      ))}
    </div>
  )
}