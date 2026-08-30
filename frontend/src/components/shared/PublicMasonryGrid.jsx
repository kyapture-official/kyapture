// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/shared/PublicMasonryGrid.jsx
import React, { useState } from "react";
import { useInView } from "react-intersection-observer";
import { formatDuration } from "../../utils/formatters";
import { getBlurhashDataUrl } from "../../utils/blurhashDataUrl";

/**
 * Appends the client's unlock token to a download_url, matching the same
 * ?token= convention clientsApi.getGallery() already uses. download_url
 * from the backend is deliberately token-less — see
 * PublicMediaAssetSerializer.get_download_url for why.
 */
function buildDownloadHref(downloadUrl, token) {
  if (!downloadUrl) return null;
  return token
    ? `${downloadUrl}?token=${encodeURIComponent(token)}`
    : downloadUrl;
}

function DownloadIcon({ className }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
      />
    </svg>
  );
}

function CheckIcon({ className }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={3}
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

const PLAY_ICON = (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="white"
    aria-hidden="true"
  >
    <path d="M8 5v14l11-7z" />
  </svg>
);

/**
 * Individual image renderer managing intersection observation,
 * aspect-ratio containment, state-synchronization, and asset-theft protection.
 */
function LazyPhoto({
  photo,
  index,
  token,
  onPhotoClick,
  isSelected,
  onToggleSelection,
}) {
  const [loadedSrc, setLoadedSrc] = useState(null);
  const [errorSrc, setErrorSrc] = useState(null);

  const isVideo = photo.media_type === "video";

  const downloadHref = buildDownloadHref(photo.download_url, token);

  // Videos have no thumbnail_url/display_url — those are image-only
  // derived variants. poster_url is the generated frame grab.
  const imgSrc = isVideo
    ? photo.poster_url
    : photo.thumbnail_url || photo.display_url;

  const isLoaded = loadedSrc === imgSrc;
  // Guard against both being undefined/null "matching" and producing a
  // false-positive error state — this was the exact bug behind the
  // "Unavailable" placeholder video assets were hitting.
  const hasError = errorSrc === imgSrc && imgSrc != null;

  // Videos never get a blurhash (only process_image_pipeline computes one),
  // so this is null for video assets — no placeholder, no regression.
  const blurDataUrl = getBlurhashDataUrl(photo.blurhash);

  const { ref, inView } = useInView({
    triggerOnce: true,
    rootMargin: "200px 0px",
  });

  const aspectRatio =
    photo.width && photo.height ? `${photo.width} / ${photo.height}` : "3 / 2";

  const handleContextMenu = (e) => e.preventDefault();

  // No thumbnail yet because the asset is still processing (not because
  // something actually failed) — show a quiet placeholder instead of the
  // scary "Unavailable" state. Applies to images too: they go through the
  // same async pending→ready window, just usually fast enough not to be
  // noticed by the time a client opens the link.
  const stillProcessing =
    !imgSrc &&
    (photo.processing_status === "pending" ||
      photo.processing_status === "processing");

  return (
    <div
      ref={ref}
      onClick={() => !stillProcessing && onPhotoClick?.(index)}
      className={`group relative w-full overflow-hidden rounded-lg bg-cream-100 mb-3 break-inside-avoid shadow-sm hover:shadow-md transition-shadow duration-300 select-none ${
        stillProcessing ? "" : "cursor-pointer"
      }`}
      style={{
        aspectRatio,
        ...(blurDataUrl &&
          !isLoaded && {
            backgroundImage: `url(${blurDataUrl})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }),
      }}
      onContextMenu={handleContextMenu}
    >
      {inView ? (
        <>
          {stillProcessing ? (
            <div className="absolute inset-0 bg-cream-100 animate-pulse flex items-center justify-center">
              <span className="text-cream-400 text-[10px] font-light select-none">
                Processing…
              </span>
            </div>
          ) : hasError ? (
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
            // 🎬 CLAUDE LE DEKO VIDEO LOGIC YAHA MERGE GARIEKO CHHA
            <>
              <img
                src={imgSrc}
                alt={photo.alt || photo.original_name || "Gallery item"}
                loading="lazy"
                decoding="async"
                className={`
                  w-full h-full object-cover pointer-events-none
                  transition-[opacity,transform] duration-500 ease-out
                  group-hover:scale-[1.03]
                  ${isLoaded ? "opacity-100" : "opacity-0"}
                `}
                style={{
                  WebkitTouchCallout: "none",
                  WebkitUserSelect: "none",
                }}
                onLoad={() => setLoadedSrc(imgSrc)}
                onError={() => setErrorSrc(imgSrc)}
              />

              {/* Video Play Icon */}
              {isVideo && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="w-11 h-11 rounded-full bg-black/50 flex items-center justify-center backdrop-blur-sm">
                    {PLAY_ICON}
                  </div>
                </div>
              )}

              {/* Video Duration */}
              {isVideo && photo.duration != null && (
                <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/70 text-white text-[10px] font-medium tabular-nums pointer-events-none">
                  {formatDuration(photo.duration)}
                </span>
              )}
            </>
          )}

          <div
            className={`absolute inset-0 bg-black/5 transition-opacity duration-300 pointer-events-none ${
              isSelected
                ? "opacity-100 bg-black/10"
                : "opacity-0 group-hover:opacity-100"
            }`}
          />

          {/* Selection Checkbox Toggle */}
          {onToggleSelection && photo.id && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleSelection(photo.id);
              }}
              onContextMenu={(e) => e.stopPropagation()}
              className={`absolute top-2 left-2 z-10 w-6 h-6 rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink ${
                isSelected
                  ? "bg-ink text-white opacity-100 ring-2 ring-white scale-100"
                  : "bg-black/30 text-white opacity-0 group-hover:opacity-100 hover:bg-black/50 scale-95 hover:scale-100"
              }`}
              aria-label={isSelected ? "Deselect item" : "Select item"}
              title={isSelected ? "Deselect item" : "Select item"}
            >
              <CheckIcon className="w-3.5 h-3.5" />
            </button>
          )}

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
  );
}

export default function PublicMasonryGrid({
  photos,
  token,
  onPhotoClick,
  selectedAssetIds = new Set(),
  onToggleSelection,
}) {
  if (!photos || photos.length === 0) return null;

  return (
    <div className="columns-2 sm:columns-3 lg:columns-4 xl:columns-5 gap-3 p-1 w-full mx-auto">
      {photos.map((photo, index) => (
        <LazyPhoto
          key={photo.id ?? index}
          photo={photo}
          index={index}
          token={token}
          onPhotoClick={onPhotoClick}
          isSelected={selectedAssetIds?.has(photo.id)}
          onToggleSelection={onToggleSelection}
        />
      ))}
    </div>
  );
}
