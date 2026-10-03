// File Location: frontend/src/components/shared/PhotoLightbox.jsx

import React, {
  useEffect,
  useLayoutEffect,
  useState,
  useRef,
  useCallback,
} from "react";
import { createPortal } from "react-dom";
import Spinner from "../ui/Spinner";

const SLIDESHOW_INTERVAL_MS = 4000;

export default function PhotoLightbox({
  photos,
  index,
  token,
  onClose,
  onChange,
  videoAccessToken,
  onDownload,
  // Phase 3 — favorites (client-facing gallery only; dashboard's own
  // PhotoGrid usage never passes these, so the button simply doesn't render).
  isFavorited,
  onToggleFavorite,
  // Phase 3 — slideshow. `slideshowMode` starts autoplay immediately on
  // open (the "Slideshow" entry point); the play/pause button works
  // either way once open.
  slideshowMode = false,
}) {
  const [imageLoading, setImageLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [isPlaying, setIsPlaying] = useState(slideshowMode);
  const touchStartX = useRef(0);
  const touchEndX = useRef(0);
  const dialogRef = useRef(null);
  const previousFocusRef = useRef(null);

  /**
   * Ref-stable mirror of the photos prop to isolate preloading loops from parent reference churn.
   */
  const photosRef = useRef(photos);
  useEffect(() => {
    photosRef.current = photos;
  });

  const activePhoto = photos[index];
  const isVideo = activePhoto.media_type === "video";

    // Dashboard payloads include original_url (the real file — safe, since
  // the cookie session already proves ownership). Public/client payloads
  // never include original_url (see PublicMediaAssetSerializer); they get
  // playback_url instead, pointing at PublicVideoStreamView, which needs
  // the gallery's unlock token appended as a query param for
  // password-protected galleries — browsers can't attach a custom
  // Authorization header to a <video src>.
  const videoSrc = isVideo
    ? activePhoto.original_url
      || (activePhoto.playback_url
            ? videoAccessToken
              ? `${activePhoto.playback_url}${activePhoto.playback_url.includes('?') ? '&' : '?'}token=${encodeURIComponent(videoAccessToken)}`
              : activePhoto.playback_url
            : null)
    : null

  const downloadHref = activePhoto?.download_url
    ? token
      ? `${activePhoto.download_url}?token=${encodeURIComponent(token)}`
      : activePhoto.download_url
    : null;

  // Synchronize loading and error state metrics with current image index values.
  // useLayoutEffect is utilized here to reset visual parameters synchronously before paint
  // to prevent transient single-frame leaks of prior images during unmount/remount commits.
  useLayoutEffect(() => {
    setImageLoading(true);
    setHasError(false);
  }, [index]);

  /**
   * Captures the active focus target, applies programmatic focus, and handles focus trapping.
   */
  useEffect(() => {
    previousFocusRef.current = document.activeElement;
    dialogRef.current?.focus();
    return () => {
      previousFocusRef.current?.focus();
    };
  }, []);

  const handleNext = useCallback(() => {
    if (index < photos.length - 1) {
      onChange?.(index + 1);
    }
  }, [index, photos.length, onChange]);

  // ── SLIDESHOW AUTOPLAY (Phase 3) ────────────────────────────────────────
  // Loops back to the first photo at the end — a real "slideshow" rather
  // than one that silently stops. Pauses itself (without clearing
  // isPlaying — resumes automatically once past the video) while the
  // current slide is a video: auto-advancing on a fixed timer while a
  // video is trying to play would cut it off mid-playback.
  useEffect(() => {
    if (!isPlaying || isVideo) return;
    const id = setInterval(() => {
      onChange?.((index + 1) % photos.length);
    }, SLIDESHOW_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, isVideo, index, photos.length]);

  const handlePrev = useCallback(() => {
    if (index > 0) {
      onChange?.(index - 1);
    }
  }, [index, onChange]);

  /**
   * Preloads adjacent images to keep slide transitions feeling instantaneous.
   * Leverages photosRef to prevent dependency-triggered execution loops.
   */
  useEffect(() => {
    const currentPhotos = photosRef.current;
    if (!currentPhotos) return;

    const preloadIndices = [index - 1, index + 1];
    preloadIndices.forEach((i) => {
      if (i >= 0 && i < currentPhotos.length) {
        const neighbor = currentPhotos[i];
        if (neighbor.media_type === "video") return; // can't preload video via Image()
        const img = new Image();
        img.src = neighbor.display_url;
      }
    });
  }, [index]);

  /**
   * Freezes background scrolling on mount and restores original inline overflow style on unmount.
   */
  useEffect(() => {
    const originalStyle = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalStyle;
    };
  }, []);

  /**
   * Returns the focusable elements currently reachable by keyboard Tab inside the dialog.
   * Filters out elements hidden via display: none or visibility: hidden using modern
   * checkVisibility() with a robust fallback to prevent focus from leaking into back-page layers.
   */
  const getFocusableElements = useCallback(() => {
    const candidates = dialogRef.current?.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (!candidates) return [];

    return Array.from(candidates).filter((el) => {
      if (typeof el.checkVisibility === "function") {
        return el.checkVisibility({ checkVisibilityCSS: true });
      }
      // Fallback for older layout engines lacking checkVisibility support
      if (el.getClientRects().length === 0) return false;
      return window.getComputedStyle(el).visibility !== "hidden";
    });
  }, []);

  /**
   * Global keyboard input processing (including native focus trapping).
   */
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose?.();
      } else if (e.key === "ArrowRight") {
        handleNext();
      } else if (e.key === "ArrowLeft") {
        handlePrev();
      } else if (e.key === " " && !isVideo) {
        // Spacebar toggles slideshow play/pause — skipped for a video
        // slide, where space is the natural "play/pause the video" key
        // the native <video controls> element already owns.
        e.preventDefault();
        setIsPlaying((prev) => !prev);
      } else if (e.key === "Tab") {
        // Native modal focus trap to prevent keyboard leaks into background layout.
        const focusableElements = getFocusableElements();
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          // Tab + Shift
          if (document.activeElement === firstElement) {
            lastElement.focus();
            e.preventDefault();
          }
        } else {
          // Tab
          if (document.activeElement === lastElement) {
            firstElement.focus();
            e.preventDefault();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleNext, handlePrev, onClose, getFocusableElements, isVideo]);

  /**
   * Native Touch Gestures (Swipe to Navigate)
   */
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
    touchEndX.current = e.touches[0].clientX;
  };

  const handleTouchMove = (e) => {
    touchEndX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = () => {
    const swipeDistance = touchStartX.current - touchEndX.current;
    const swipeThreshold = 50;

    if (Math.abs(swipeDistance) > swipeThreshold) {
      if (swipeDistance > 0) {
        handleNext(); // Swipe Left -> Load Next
      } else {
        handlePrev(); // Swipe Right -> Load Prev
      }
    }
  };

  const handleContextMenu = (e) => e.preventDefault();

  if (!activePhoto) return null;

  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      tabIndex={-1} // Allow programmatic focus targeting
      className="fixed inset-0 z-[100] flex flex-col justify-between bg-black/95 select-none focus:outline-none"
      onClick={onClose}
    >
      {/* Top Header Controls */}
      <header className="flex items-center justify-between px-6 py-4 w-full bg-gradient-to-b from-black/60 to-transparent pointer-events-none z-10">
        <span className="text-white/60 text-xs tracking-widest font-light">
          {index + 1} / {photos.length}
        </span>

                <div className="flex items-center gap-1 pointer-events-auto">
          {!isVideo && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsPlaying((prev) => !prev);
              }}
              className="p-2 text-white/70 hover:text-white transition-colors duration-200 focus:outline-none"
              aria-label={isPlaying ? "Pause slideshow" : "Play slideshow"}
              title={isPlaying ? "Pause slideshow" : "Play slideshow"}
            >
              {isPlaying ? (
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="6" y="5" width="4" height="14" rx="1" />
                  <rect x="14" y="5" width="4" height="14" rx="1" />
                </svg>
              ) : (
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>
          )}
          {onToggleFavorite && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite(activePhoto.id);
              }}
              className={`p-2 transition-colors duration-200 focus:outline-none ${
                isFavorited ? "text-red-500" : "text-white/70 hover:text-white"
              }`}
              aria-label={isFavorited ? "Remove from favorites" : "Add to favorites"}
              title={isFavorited ? "Remove from favorites" : "Add to favorites"}
            >
              <svg
                className="w-6 h-6"
                viewBox="0 0 24 24"
                fill={isFavorited ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth={isFavorited ? 0 : 1.5}
                aria-hidden="true"
              >
                <path d="M12 21s-6.716-4.35-9.428-8.06C.665 10.42 1.1 6.9 3.6 5.1c2.02-1.46 4.63-1.02 6.17.86L12 8.2l2.23-2.24c1.54-1.88 4.15-2.32 6.17-.86 2.5 1.8 2.935 5.32 1.028 7.84C18.716 16.65 12 21 12 21z" />
              </svg>
            </button>
          )}
          {onDownload ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDownload(activePhoto);
              }}
              className="p-2 text-white/70 hover:text-white transition-colors duration-200 focus:outline-none"
              aria-label="Download this photo"
              title="Download photo"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
            </button>
          ) : (
            downloadHref && (
              <a
                href={downloadHref}
                onClick={(e) => e.stopPropagation()}
                className="p-2 text-white/70 hover:text-white transition-colors duration-200 focus:outline-none"
                aria-label="Download this photo"
                title="Download photo"
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                  />
                </svg>
              </a>
            )
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClose?.();
            }}
            className="p-2 text-white/70 hover:text-white transition-colors duration-200 focus:outline-none"
            aria-label="Close Lightbox"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      </header>

      {/* Main Image Container Area */}
      <div
        className="relative flex-1 min-h-0 flex items-center justify-center px-4 md:px-16"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Left Arrow Navigation Button */}
        {index > 0 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handlePrev();
            }}
            className="absolute left-4 z-10 hidden md:flex items-center justify-center w-12 h-12 rounded-full bg-black/20 hover:bg-black/40 text-white/70 hover:text-white border border-white/10 hover:border-white/20 transition-all duration-200"
            aria-label="Previous Photo"
          >
            <svg
              className="w-5 h-5 mr-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
          </button>
        )}

        {/* Loading Spinner Overlaid on Active Viewport */}
        {imageLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Spinner className="w-8 h-8 text-white/50" />
          </div>
        )}

        {/* Main Photo Visual Element */}
        <div
          className="relative h-full w-full flex items-center justify-center"
          onClick={(e) => e.stopPropagation()}
        >
          {hasError ? (
            <div
              role="alert"
              className="flex flex-col items-center justify-center p-8 text-center text-white/50 bg-black/40 rounded-xl border border-white/5 backdrop-blur-sm"
            >
              <svg
                className="w-8 h-8 text-white/30 mb-2"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <p className="text-xs font-light tracking-wide select-none">
                {isVideo
                  ? "This video is temporarily unavailable"
                  : "This image is temporarily unavailable"}
              </p>
            </div>
          ) : isVideo ? (
            // stream_url is a model field reserved for future HLS support,
            // but nothing in the pipeline ever populates it —
            // process_video_asset only writes poster_image, preview_file,
            // and duration. original_url (the real uploaded file) is the
            // only working playback source today. Swap to stream_url once
            // real adaptive streaming exists.
            <video
              key={index}
              src={videoSrc}
              poster={activePhoto.poster_url || undefined}
              controls
              playsInline
              onContextMenu={handleContextMenu}
              onClick={(e) => e.stopPropagation()}
              onLoadedData={() => setImageLoading(false)}
              onError={() => {
                setImageLoading(false);
                setHasError(true);
              }}
              className={`
                max-h-full max-w-full select-none transition-all duration-300 ease-out
                ${imageLoading ? "opacity-0 scale-95 blur-sm" : "opacity-100 scale-100 blur-0"}
              `}
            />
          ) : (
            <img
              key={index}
              src={activePhoto.display_url}
              srcSet={
                [
                  activePhoto.medium_url ? `${activePhoto.medium_url} 1280w` : null,
                  activePhoto.display_url ? `${activePhoto.display_url} 2048w` : null,
                ]
                  .filter(Boolean)
                  .join(", ") || undefined
              }
              sizes="100vw"
              alt={
                activePhoto.alt ||
                activePhoto.original_name ||
                "Fullscreen view"
              }
              draggable={false}
              onContextMenu={handleContextMenu}
              onLoad={() => setImageLoading(false)}
              onError={() => {
                setImageLoading(false);
                setHasError(true);
              }}
              className={`
                max-h-full max-w-full object-contain pointer-events-none select-none transition-all duration-300 ease-out
                ${imageLoading ? "opacity-0 scale-95 blur-sm" : "opacity-100 scale-100 blur-0"}
              `}
              style={{
                WebkitTouchCallout: "none",
              }}
            />
          )}
        </div>

        {/* Right Arrow Navigation Button */}
        {index < photos.length - 1 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleNext();
            }}
            className="absolute right-4 z-10 hidden md:flex items-center justify-center w-12 h-12 rounded-full bg-black/20 hover:bg-black/40 text-white/70 hover:text-white border border-white/10 hover:border-white/20 transition-all duration-200"
            aria-label="Next Photo"
          >
            <svg
              className="w-5 h-5 ml-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Footer Title Metadata Bar */}
      <footer className="w-full text-center px-6 py-6 bg-gradient-to-t from-black/60 to-transparent pointer-events-none z-10">
        <p className="text-white/80 text-sm font-light select-none tracking-wide max-w-xl mx-auto truncate">
          {activePhoto.original_name || "Untitled Image"}
        </p>
      </footer>
    </div>,
    document.body,
  );
}
