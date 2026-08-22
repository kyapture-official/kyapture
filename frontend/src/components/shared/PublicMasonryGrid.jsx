// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/shared/PublicMasonryGrid.jsx
import React, { useState } from 'react'
import { useInView } from 'react-intersection-observer'

/**
 * Appends the client's unlock token to a download_url, matching the same
 * ?token= convention clientsApi.getGallery() already uses. download_url
 * from the backend is deliberately token-less — see
 * PublicMediaAssetSerializer.get_download_url for why.
 */
function buildDownloadHref(downloadUrl, token) {
  if (!downloadUrl) return null
  return token ? `${downloadUrl}?token=${encodeURIComponent(token)}` : downloadUrl
}

function DownloadIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  )
}

/**
 * Individual image renderer managing intersection observation,
 * aspect-ratio containment, state-synchronization, and asset-theft protection.
 */
function LazyPhoto({ photo, index, token, onPhotoClick }) {
  const [loadedSrc, setLoadedSrc] = useState(null)
  const [errorSrc,  setErrorSrc]  = useState(null)

  const imgSrc = photo.thumbnail_url || photo.display_url
  const downloadHref = buildDownloadHref(photo.download_url, token)

  const isLoaded = loadedSrc === imgSrc
  const hasError = errorSrc  === imgSrc

  const { ref, inView } = useInView({
    triggerOnce: true,
    rootMargin: '200px 0px',
  })

  const aspectRatio =
    photo.width && photo.height ? `${photo.width} / ${photo.height}` : '3 / 2'

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
              src={imgSrc}
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
              onLoad={() => setLoadedSrc(imgSrc)}
              onError={() => setErrorSrc(imgSrc)}
            />
          )}
          <div className="absolute inset-0 bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

          {/* Only renders when the backend actually returned a download_url —
              i.e. only when the photographer enabled downloads for this gallery. */}
          {downloadHref && (
            <a
              href={downloadHref}
              onClick={(e) => e.stopPropagation()}
              onContextMenu={(e) => e.stopPropagation()}
              className="absolute top-2 right-2 z-10 p-2 rounded-full bg-white/90 text-ink
                        opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                        transition-opacity duration-200 hover:bg-white shadow-sm
                        focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
              aria-label="Download this photo"
              title="Download photo"
            >
              <DownloadIcon className="w-4 h-4" />
            </a>
          )}
        </>
      ) : (
        <div className="w-full h-full bg-cream-100 animate-pulse" />
      )}
    </div>
  )
}

export default function PublicMasonryGrid({ photos, token, onPhotoClick }) {
  if (!photos || photos.length === 0) return null

  return (
    <div className="columns-2 sm:columns-3 lg:columns-4 xl:columns-5 gap-3 p-1 w-full mx-auto">
      {photos.map((photo, index) => (
        <LazyPhoto
          key={photo.id ?? index}
          photo={photo}
          index={index}
          token={token}
          onPhotoClick={onPhotoClick}
        />
      ))}
    </div>
  )
}