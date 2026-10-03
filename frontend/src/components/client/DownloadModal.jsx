// File Location: frontend/src/components/client/DownloadModal.jsx
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import DownloadForm from "./DownloadForm";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * The client "Download" dialog (Pixieset-style): choose High Resolution vs
 * Web Size and, only when authorization is actually needed, give an email
 * and the download PIN. Opened by an explicit Download click from the
 * gallery toolbar, a photo tile, or the lightbox — never on gallery entry.
 *
 * Self-contained portal rather than ui/Modal: it must stack above the photo
 * lightbox (z-[100]), and it has to swallow keyboard events while open so
 * typing an email doesn't toggle the lightbox slideshow (Space) or flip
 * photos (arrow keys) underneath it.
 */
export default function DownloadModal({
  open,
  onClose,
  username,
  slug,
  galleryToken,
  hasDownloadPin,
  downloadPolicy,
  target,
  photoSets,
  photoCount,
}) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = requestAnimationFrame(() => {
      dialogRef.current?.querySelector(FOCUSABLE)?.focus();
    });

    // Runs on `document`, i.e. before the lightbox's `window` listener, so
    // stopping propagation here keeps every key inside the dialog.
    const handleKeyDown = (event) => {
      event.stopPropagation();
      if (event.key === "Escape") {
        onCloseRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialogRef.current.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [open]);

  if (!open || !target) return null;

  const title = target.type === "photo" ? "Download photo" : "Download";

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={() => onCloseRef.current?.()}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="download-modal-title"
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-cream-200 bg-surface-light shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-cream-200 px-6 pb-4 pt-5">
          <h3 id="download-modal-title" className="font-serif text-xl text-ink">
            {title}
          </h3>
          <button
            type="button"
            onClick={() => onCloseRef.current?.()}
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
            aria-label="Close download dialog"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5">
          <DownloadForm
            // Re-mount per target so scope/size/error state never leaks
            // from one download into the next.
            key={target.type === "photo" ? target.photo?.id : `gallery:${target.setId || ""}`}
            username={username}
            slug={slug}
            galleryToken={galleryToken}
            hasDownloadPin={hasDownloadPin}
            downloadPolicy={downloadPolicy}
            target={target}
            photoSets={photoSets}
            photoCount={photoCount}
            onCancel={() => onCloseRef.current?.()}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
