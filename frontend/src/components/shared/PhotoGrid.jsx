// File Location: frontend/src/components/shared/PhotoGrid.jsx

import { useState } from "react";
import PhotoLightbox from "./PhotoLightbox";
import { formatBytes } from "../../utils/formatters";

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

// Six-dot grip icon — signals "drag me" without borrowing the delete/cover
// icon language already used in the other two corners.
const DRAG_HANDLE_ICON = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="9" cy="6" r="1.6" />
    <circle cx="9" cy="12" r="1.6" />
    <circle cx="9" cy="18" r="1.6" />
    <circle cx="15" cy="6" r="1.6" />
    <circle cx="15" cy="12" r="1.6" />
    <circle cx="15" cy="18" r="1.6" />
  </svg>
);

export default function PhotoGrid({
  photos = [],
  onDelete,
  onSetCover,
  onReorder,
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
  const [draggedIndex, setDraggedIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const canReorder = showActions && typeof onReorder === "function";


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

  // ── DRAG-AND-DROP HANDLERS ────────────────────────────────────────────
  const resetDragState = () => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // Fired on the grip handle only — the handle is the sole draggable
  // element, not the card, so an ordinary click on the thumbnail can never
  // be misread as a drag attempt.
  const handleDragStart = (e, index) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
    // Firefox refuses to start a drag at all unless setData is called.
    e.dataTransfer.setData("text/plain", String(index));

    // Drag the whole card as the ghost image, not just the tiny grip icon
    // the user actually grabbed — much clearer feedback about what's moving.
    const card = e.currentTarget.closest("[data-photo-card]");
    if (card) {
      e.dataTransfer.setDragImage(card, card.offsetWidth / 2, card.offsetHeight / 2);
    }
  };

  const handleDragEnter = (e, index) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;
    setDragOverIndex(index);
  };

  // Must call preventDefault or the browser refuses to allow a drop here
  // at all — this is a real HTML5 DnD spec requirement, not a style choice.
  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (e, dropIndex) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === dropIndex) {
      resetDragState();
      return;
    }

    // Splice-move within the FULL photos array (not just what's visible),
    // then hand the complete reordered array to the parent. The parent is
    // responsible for the optimistic setState + API call + rollback —
    // this component only knows about drag mechanics, not persistence.
    const reordered = [...photos];
    const [moved] = reordered.splice(draggedIndex, 1);
    reordered.splice(dropIndex, 0, moved);

    resetDragState();
    onReorder?.(reordered);
  };

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
        {photos.map((photo, idx) => {
          const isBroken = brokenIds.has(photo.id);

          return (
            <div
              key={photo.id}
              data-photo-card
              tabIndex={0}
              role="button"
              aria-label={`View ${photo.title || photo.original_name || "Photo"}`}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              onClick={() => setLightbox(idx)}
              onDragEnter={(e) => handleDragEnter(e, idx)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, idx)}
              className={`group relative overflow-hidden rounded-xl cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 transition-all bg-cream-100 ${
              dragOverIndex === idx ? "ring-2 ring-ink scale-95" : ""
            }`}
              style={{
                animation: "photoGridFadeUp 0.3s ease-out both",
                animationDelay: `${idx * 0.04}s`,
              }}
            >
              {isBroken ? (
                // BUG FIX: previously silently swapped a broken photo for a
                // random stock image (photo-1544005313-...) with no
                // indication anything failed. A photographer or client would
                // see an unrelated stock photo standing in for their real
                // one and have no way to know it never loaded. This now
                // shows an honest "failed to load" state instead.
                <div className="w-full h-48 flex flex-col items-center justify-center gap-2 text-muted bg-cream-100">
                  {BROKEN_IMAGE_ICON}
                  <span className="text-[10px] font-medium">
                    Failed to load
                  </span>
                </div>
              ) : (
                <img
                  src={
                    photo.thumbnail_url ||
                    photo.display_url ||
                    photo.original_url
                  }
                  alt={photo.title || photo.original_name || "Collection asset"}
                  className="w-full h-48 object-cover block transition-transform duration-500 group-hover:scale-105"
                  loading="lazy"
                  onError={() => markBroken(photo.id)}
                />
              )}

              <div className="absolute inset-0 bg-ink/0 group-hover:bg-ink/30 transition-all duration-300 rounded-xl pointer-events-none" />

              {showActions && onDelete && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(photo.id);
                  }}
                  className="absolute top-2 right-2 p-1.5 rounded-lg bg-white/95 text-red-500
                            opacity-0 group-hover:opacity-100 transition-opacity duration-200
                            hover:bg-red-50 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 shadow-sm cursor-pointer"
                  aria-label={`Delete ${photo.title || photo.original_name || "photo"}`}
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              )}

              {/* NEW: set-as-cover action, top-left so it doesn't collide with delete (top-right) */}
              {showActions && onSetCover && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSetCover(photo.id);
                  }}
                  className="absolute top-2 left-2 p-1.5 rounded-lg bg-white/95 text-ink
                            opacity-0 group-hover:opacity-100 transition-opacity duration-200
                            hover:bg-cream-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink shadow-sm cursor-pointer"
                  aria-label={`Set ${photo.title || photo.original_name || "photo"} as gallery cover`}
                  title="Set as cover"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M11.48 3.5a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.563.563 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
                    />
                  </svg>
                </button>
              )}

              {/* drag-to-reorder handle — top-center, the one corner not
                  already claimed by delete or set-cover */}
              {canReorder && !isBroken && (
                <div
                  draggable
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragEnd={resetDragState}
                  onClick={(e) => e.stopPropagation()}
                  aria-hidden="true"
                  title="Drag to reorder"
                  className="absolute top-2 left-1/2 -translate-x-1/2 z-10 p-1.5 rounded-lg bg-white/95 text-ink/50
                            opacity-0 group-hover:opacity-100 transition-opacity duration-200
                            hover:bg-cream-100 hover:text-ink shadow-sm cursor-grab active:cursor-grabbing"
                >
                  {DRAG_HANDLE_ICON}
                </div>
              )}

              {!isBroken && (
                <div
                  className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-ink/70 to-transparent
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
        />
      )}
    </>
  );
}
