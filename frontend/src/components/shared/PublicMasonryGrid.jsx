// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/shared/PublicMasonryGrid.jsx
import React, { useState } from "react";
import { useInView } from "react-intersection-observer";
import { Download, Heart, Share2 } from "lucide-react";
import { buildClientGalleryUrl, formatDuration } from "../../utils/formatters";
import { getBlurhashDataUrl } from "../../utils/blurhashDataUrl";
import { useToast } from "../ui/Toast";

/**
 * Appends the client's unlock token to a download_url, matching the same
 * ?token= convention clientsApi.getGallery() already uses. download_url
 * from the backend is deliberately token-less — see
 * PublicMediaAssetSerializer.get_download_url for why.
 */
function buildDownloadHref(downloadUrl, token) {
  if (!downloadUrl) return null;
  return token
    ? `${downloadUrl}${downloadUrl.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`
    : downloadUrl;
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
  username,
  slug,
  onPhotoClick,
  fixedAspect = null,
  isFavorited = false,
  onToggleFavorite,
  allowDownload = false,
}) {
  const [loadedSrc, setLoadedSrc] = useState(null);
  const [errorSrc, setErrorSrc] = useState(null);
  const toast = useToast();

  const isVideo = photo.media_type === "video";

  const downloadHref = allowDownload ? buildDownloadHref(photo.download_url, token) : null;

  // Videos have no thumbnail_url/display_url/medium_url — those are
  // image-only derived variants. poster_url is the generated frame grab.
  const imgSrc = isVideo
    ? photo.poster_url
    : photo.thumbnail_url || photo.medium_url || photo.display_url;

  // Responsive image selection (Phase 2, item A): lets the browser pick
  // the smallest derivative that still covers its actual rendered size
  // instead of every grid cell downloading the full 2048px display
  // variant. Video posters have no size tiers, so this is image-only.
  // `sizes` mirrors this grid's intentionally spacious client-gallery
  // breakpoints — one larger editorial image per rendered column.
  const imgSrcSet = !isVideo
    ? [
        photo.thumbnail_url ? `${photo.thumbnail_url} 640w` : null,
        photo.medium_url ? `${photo.medium_url} 1280w` : null,
        photo.display_url ? `${photo.display_url} 2048w` : null,
      ]
        .filter(Boolean)
        .join(", ") || undefined
    : undefined;
  const imgSizes = !isVideo
    ? "(min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
    : undefined;

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

  // A "horizontal" grid style (see PublicMasonryGrid below) forces a
  // uniform tile aspect ratio instead of each photo's own — that's what
  // makes it look like a distinct grid rather than the default masonry.
  const aspectRatio =
    fixedAspect ||
    (photo.width && photo.height ? `${photo.width} / ${photo.height}` : "3 / 2");

  const handleContextMenu = (e) => e.preventDefault();

  const handleShare = async (event) => {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(buildClientGalleryUrl(username, slug));
      toast("Link copied", "success");
    } catch {
      toast("Unable to copy the link.", "error");
    }
  };

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
      className={`group relative w-full overflow-hidden bg-cream-100 transition-opacity duration-300 select-none ${
        fixedAspect ? "" : "mb-3 break-inside-avoid"
      } ${stillProcessing ? "" : "cursor-pointer"}`}
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
              <span className="text-muted text-[10px] font-light select-none">
                Processing…
              </span>
            </div>
          ) : hasError ? (
            <div className="absolute inset-0 bg-cream-300 flex flex-col items-center justify-center p-4">
              <svg
                className="w-5 h-5 text-muted mb-1"
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
              <span className="text-muted text-xs font-light select-none pointer-events-none">
                Unavailable
              </span>
            </div>
          ) : (
            // 🎬 CLAUDE LE DEKO VIDEO LOGIC YAHA MERGE GARIEKO CHHA
            <>
              <img
                src={imgSrc}
                srcSet={imgSrcSet}
                sizes={imgSizes}
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
                <span className="absolute bottom-2 left-2 px-1.5 py-0.5 rounded bg-black/70 text-white text-[10px] font-medium tabular-nums pointer-events-none">
                  {formatDuration(photo.duration)}
                </span>
              )}
            </>
          )}

          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/50 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100 [@media(hover:none)]:opacity-100" />

          <div className="absolute bottom-2 right-2 z-10 flex items-center gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
            {onToggleFavorite && photo.id && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleFavorite(photo.id);
                }}
                onContextMenu={(e) => e.stopPropagation()}
                className={`rounded p-2 transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-white ${
                  isFavorited
                    ? "bg-red-500 text-white"
                    : "bg-black/35 text-white hover:bg-black/55"
                }`}
                aria-label={isFavorited ? "Remove from favorites" : "Add to favorites"}
                title={isFavorited ? "Remove from favorites" : "Add to favorites"}
              >
                <Heart className={`h-4 w-4 ${isFavorited ? "fill-current" : ""}`} />
              </button>
            )}

            {downloadHref && (
              <a
                href={downloadHref}
                download={photo.original_name || true}
                onClick={(e) => e.stopPropagation()}
                onContextMenu={(e) => e.stopPropagation()}
                className="rounded bg-black/35 p-2 text-white transition-colors hover:bg-black/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                aria-label="Download this photo"
                title="Download photo"
              >
                <Download className="h-4 w-4" />
              </a>
            )}

            <button
              type="button"
              onClick={handleShare}
              onContextMenu={(e) => e.stopPropagation()}
              className="rounded bg-black/35 p-2 text-white transition-colors hover:bg-black/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
              aria-label="Share photo"
              title="Share photo"
            >
              <Share2 className="h-4 w-4" />
            </button>
          </div>
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
  username,
  slug,
  onPhotoClick,
  // Phase 2, item E — grid behavior/density driven by the gallery's
  // persisted design_settings (see utils/designSettings.js). Defaults
  // reproduce the grid's original fixed layout exactly, so a gallery
  // with no design_settings (or an older one saved before this existed)
  // renders identically to before.
  gridStyle = "vertical",
  thumbSize = "regular",
  gridSpacing = 12,
  favoritedIds = new Set(),
  onToggleFavorite,
  allowDownload = false,
}) {
  if (!photos || photos.length === 0) return null;

  // "vertical" (default) keeps the original CSS multi-column masonry —
  // each tile keeps its own photo's natural aspect ratio. "horizontal"
  // switches to a uniform CSS grid of fixed-aspect tiles instead, a
  // visibly distinct "grid" look per the Design page's own Grid Style
  // option (GalleryDesignPage.jsx).
  const isHorizontal = gridStyle === "horizontal";
  // The public gallery deliberately favors fewer, larger images. The
  // photographer's saved "large" option remains even more spacious.
  const columnClasses = isHorizontal
    ? thumbSize === "large"
      ? "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    : thumbSize === "large"
      ? "columns-1 sm:columns-2 lg:columns-3 xl:columns-4"
      : "columns-1 sm:columns-2 lg:columns-3 xl:columns-4";

  return (
    <div
      className={`${columnClasses} p-1 w-full mx-auto`}
      style={isHorizontal ? { gap: `${gridSpacing}px` } : { columnGap: `${gridSpacing}px` }}
    >
      {photos.map((photo, index) => (
        <LazyPhoto
          key={photo.id ?? index}
          photo={photo}
          index={index}
          token={token}
          username={username}
          slug={slug}
          onPhotoClick={onPhotoClick}
          fixedAspect={isHorizontal ? "4 / 3" : null}
          isFavorited={favoritedIds?.has(photo.id)}
          onToggleFavorite={onToggleFavorite}
          allowDownload={allowDownload}
        />
      ))}
    </div>
  );
}
