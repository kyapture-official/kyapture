// File Location: frontend/src/components/shared/PhotoGrid.jsx

import { useState, useRef } from "react";
import PhotoLightbox from "./PhotoLightbox";
import Spinner from "../ui/Spinner";
import { getBlurhashDataUrl } from "../../utils/blurhashDataUrl";
import { formatBytes, formatDuration } from "../../utils/formatters";
import ItemMenu from "./ItemMenu";

// ── KEYFRAME INJECTION ────────────────────────────────────────────────────
// PhotoGrid gets its own dedicated keyframe rather than reusing Toast.jsx's
// or Modal.jsx's — this keeps the entrance animation working regardless of
// which other components happen to be mounted, instead of depending on
// ToastProvider having loaded first.
if (typeof document !== "undefined") {
  const KEYFRAME_ID = "photo-grid-fade-up-keyframes";
  if (!document.getElementById(KEYFRAME_ID)) {
    const style = document.createElement("style");
    style.id = KEYFRAME_ID;
    style.textContent = `
      @media (prefers-reduced-motion: no-preference) {
        @keyframes photoGridFadeUp {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
      }
    `;
    document.head.appendChild(style);
  }
}

const BROKEN_IMAGE_ICON = (
  <svg
    width="28"
    height="28"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.5}
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M3 3l18 18M10.5 5H18a2 2 0 012 2v10.5M6 6.5V18a2 2 0 002 2h10.5M9 13l1.5-1.5a1 1 0 011.4 0L15 14.5"
    />
  </svg>
);

const PLAY_ICON = (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="white"
    aria-hidden="true"
  >
    <path d="M8 5v14l11-7z" />
  </svg>
);

/**
 * Workspace photo grid. Each tile has ONE overflow menu (top-right: Open,
 * Download, Set as cover, Move to a set, Delete permanently) and ONE heart
 * (bottom-right: the photographer's own favorite). The cover changes ONLY
 * through "Set as cover" — the heart never touches it.
 *
 *   onDelete(photo)           permanent delete (the page confirms first)
 *   onSetCover(photoId)       "Set as cover"
 *   onToggleFavorite(photo)   heart on / off
 *   onMoveToSet(photo, setId) move to another set
 *   sets / activeSetId        the collection's sets, to build "Move to …"
 */
export default function PhotoGrid({
  photos = [],
  onDelete,
  onSetCover,
  onReorder,
  onDownload,
  onToggleFavorite,
  onMoveToSet,
  sets = [],
  activeSetId = null,
  showActions = false,
}) {
  const [lightbox, setLightbox] = useState(null);
  const [brokenIds, setBrokenIds] = useState(() => new Set());

  // ── DRAG-AND-DROP REORDER STATE ──────────────────────────────────────────
  // Native HTML5 DnD, not a library — this project has no drag dependency
  // yet and the interaction here is simple enough not to need one.
  //
  // Desktop-only by nature of the API: touch browsers don't fire dragstart/
  // dragover/drop for arbitrary elements without a polyfill, so this is a
  // pointer-and-mouse feature for now, not a touch one.
  //
  // draggedIndex  — index of the card currently being dragged
  // dragOverIndex — index of the card currently under the pointer (drop target)
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const dragIndexRef = useRef(null);
  const canReorder = showActions && typeof onReorder === "function";

  const handleDragStart = (e, index) => {
    if (!canReorder) return;
    dragIndexRef.current = index;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(index));
  };

  const handleDragOver = (e, index) => {
    if (!canReorder || dragIndexRef.current === null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverIndex !== index) setDragOverIndex(index);
  };

  const handleDragLeave = (index) => {
    setDragOverIndex((prev) => (prev === index ? null : prev));
  };

  const handleDrop = (e, dropIndex) => {
    if (!canReorder) return;
    e.preventDefault();
    const dragIndex = dragIndexRef.current;
    dragIndexRef.current = null;
    setDragOverIndex(null);
    if (dragIndex === null || dragIndex === dropIndex) return;

    const reordered = [...photos];
    const [moved] = reordered.splice(dragIndex, 1);
    reordered.splice(dropIndex, 0, moved);
    onReorder(reordered.map((p) => p.id));
  };

  const handleDragEnd = () => {
    dragIndexRef.current = null;
    setDragOverIndex(null);
  };

  if (!photos.length) {
    return (
      <div className="py-20 flex flex-col items-center gap-3 text-muted">
        <svg
          className="w-12 h-12 opacity-40 text-ink"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1}
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
        <p className="text-sm font-sans font-light">
          No photos in this collection yet.
        </p>
      </div>
    );
  }

  // WCAG 2.1: lets keyboard users open the lightbox with Enter or Space
  // when a grid item is focused, without nesting an interactive element
  // inside another one.
  const handleKeyDown = (e, index) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setLightbox(index);
    }
  };

  const markBroken = (photoId) => {
    setBrokenIds((prev) => {
      const next = new Set(prev);
      next.add(photoId);
      return next;
    });
  };

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
        {photos.map((photo, idx) => {
          const isBroken = brokenIds.has(photo.id);
          const isVideo = photo.media_type === "video";
          const isFailed = photo.processing_status === "failed";
          const thumbSrc = isVideo
            ? photo.poster_url
            : photo.thumbnail_url || photo.display_url || photo.original_url;
          const showPlaceholder = !thumbSrc && !isBroken && !isFailed;
          const isDragOver = dragOverIndex === idx;
          // Only meaningful for the "actual image" render branch below —
          // broken/failed/still-processing states render their own opaque
          // content over it, so it's harmless to compute unconditionally.
          const blurDataUrl = getBlurhashDataUrl(photo.blurhash);

          return (
            <div
              key={photo.id}
              data-photo-card
              tabIndex={0}
              role="button"
              aria-label={`View ${photo.title || photo.original_name || "Photo"}`}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              onClick={() => setLightbox(idx)}
              draggable={canReorder}
              onDragStart={(e) => handleDragStart(e, idx)}
              onDragOver={(e) => handleDragOver(e, idx)}
              onDragLeave={() => handleDragLeave(idx)}
              onDrop={(e) => handleDrop(e, idx)}
              onDragEnd={handleDragEnd}
              className={`group relative overflow-hidden rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2 transition-all bg-cream-100 ${
                canReorder
                  ? "cursor-grab active:cursor-grabbing"
                  : "cursor-pointer"
              } ${dragOverIndex === idx ? "ring-2 ring-ink ring-offset-2 scale-95" : ""}`}
              style={{
                animation: "photoGridFadeUp 0.3s ease-out both",
                animationDelay: `${idx * 0.04}s`,
                ...(blurDataUrl && {
                  backgroundImage: `url(${blurDataUrl})`,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }),
              }}
            >
              {isBroken || isFailed ? (
                // BUG FIX: previously silently swapped a broken photo for a
                // random stock image (photo-1544005313-...) with no
                // indication anything failed. A photographer or client would
                // see an unrelated stock photo standing in for their real
                // one and have no way to know it never loaded. This now
                // shows an honest "failed to load" state instead.
                <div className="w-full h-48 flex flex-col items-center justify-center gap-2 text-muted bg-cream-100">
                  {BROKEN_IMAGE_ICON}
                  <span className="text-[10px] font-medium">
                    {isFailed ? "Processing failed" : "Failed to load"}
                  </span>
                </div>
              ) : showPlaceholder ? (
                <div className="w-full h-48 flex flex-col items-center justify-center gap-2 text-muted bg-cream-100">
                  <Spinner className="w-5 h-5" />
                  <span className="text-[10px] font-medium">Processing…</span>
                </div>
              ) : (
                <>
                  <img
                    src={thumbSrc}
                    alt={
                      photo.title || photo.original_name || "Collection asset"
                    }
                    className="w-full h-48 object-cover block transition-transform duration-500 group-hover:scale-105"
                    loading="lazy"
                    onError={() => markBroken(photo.id)}
                  />
                  {isVideo && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <div className="w-9 h-9 rounded-full bg-black/50 flex items-center justify-center backdrop-blur-sm">
                        {PLAY_ICON}
                      </div>
                    </div>
                  )}
                  {isVideo && photo.duration != null && (
                    <span className="absolute left-2 top-2 px-1.5 py-0.5 rounded bg-black/70 text-white text-[10px] font-medium tabular-nums pointer-events-none">
                      {formatDuration(photo.duration)}
                    </span>
                  )}
                </>
              )}

              <div className="absolute inset-0 bg-ink/0 group-hover:bg-ink/30 transition-all duration-300 rounded-xl pointer-events-none" />

              {showActions && (
                <>
                  <ItemMenu
                    className="absolute right-2 top-2 z-20"
                    label={`More actions for ${photo.title || photo.original_name || "photo"}`}
                    items={[
                      { key: "open", label: "Open", onSelect: () => setLightbox(idx) },
                      ...(onDownload && photo.original_url
                        ? [{ key: "download", label: "Download", onSelect: () => onDownload(photo) }]
                        : []),
                      ...(onSetCover && !isFailed && photo.processing_status === "ready"
                        ? [{ key: "cover", label: "Set as cover", onSelect: () => onSetCover(photo.id) }]
                        : []),
                      ...(onMoveToSet
                        ? sets
                            .filter((set) => String(set.id) !== String(activeSetId))
                            .map((set, position) => ({
                              key: `move-${set.id}`,
                              label: `Move to ${set.name}`,
                              divider: position === 0,
                              onSelect: () => onMoveToSet(photo, set.id),
                            }))
                        : []),
                      ...(onDelete
                        ? [{ key: "delete", label: "Delete permanently", danger: true, divider: true, onSelect: () => onDelete(photo) }]
                        : []),
                    ]}
                  />
                  {onToggleFavorite && !isFailed && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(photo);
                      }}
                      aria-pressed={Boolean(photo.is_favorite)}
                      aria-label={photo.is_favorite ? `Remove ${photo.original_name || "photo"} from favorites` : `Add ${photo.original_name || "photo"} to favorites`}
                      title={photo.is_favorite ? "Remove from favorites" : "Add to favorites"}
                      className={`absolute bottom-2 right-2 z-20 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full transition-all duration-150 focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
                        photo.is_favorite
                          ? "bg-white/95 text-red-500 opacity-100 shadow-sm"
                          : "bg-black/35 text-white opacity-0 hover:bg-black/55 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                      }`}
                    >
                      <svg
                        className="h-[18px] w-[18px]"
                        viewBox="0 0 24 24"
                        fill={photo.is_favorite ? "currentColor" : "none"}
                        stroke="currentColor"
                        strokeWidth={photo.is_favorite ? 0 : 1.8}
                        aria-hidden="true"
                      >
                        <path d="M12 21s-6.716-4.35-9.428-8.06C.665 10.42 1.1 6.9 3.6 5.1c2.02-1.46 4.63-1.02 6.17.86L12 8.2l2.23-2.24c1.54-1.88 4.15-2.32 6.17-.86 2.5 1.8 2.935 5.32 1.028 7.84C18.716 16.65 12 21 12 21z" />
                      </svg>
                    </button>
                  )}
                </>
              )}

              {!isBroken && (
                <div
                  className="absolute bottom-0 left-0 right-0 p-3 pr-12 bg-gradient-to-t from-ink/70 to-transparent
                                opacity-0 group-hover:opacity-100 transition-opacity duration-200 rounded-b-xl pointer-events-none"
                >
                  <p className="text-white text-xs truncate font-medium">
                    {photo.original_name}
                  </p>
                  <p className="text-white/70 text-[10px] font-light mt-0.5">
                    {formatBytes(photo.file_size)}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {lightbox !== null && (
        <PhotoLightbox
          photos={photos}
          index={lightbox}
          onClose={() => setLightbox(null)}
          onChange={setLightbox}
          onDownload={onDownload}
        />
      )}
    </>
  );
}
