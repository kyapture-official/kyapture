// File Location: frontend/src/components/client/ClientDialog.jsx
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * The guest-facing dialog shell (download flow, favorites): a centered card on
 * tablets/desktops and a full-width BOTTOM SHEET on phones.
 *
 * Header = the gallery's title with the photographer's name beneath it;
 * footer = "Powered by KYAPTURE". Both are the same everywhere a guest sees a
 * dialog, so the gallery owner's brand reads first and ours reads last.
 *
 * Self-contained portal rather than ui/Modal: it must stack above the photo
 * lightbox (z-[100]) and swallow keyboard events while open, so typing an email
 * never toggles the lightbox slideshow (Space) or flips photos (arrow keys)
 * underneath it.
 */
export default function ClientDialog({
  open,
  onClose,
  galleryTitle,
  photographerName,
  heading,
  size = "md",
  children,
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

  if (!open) return null;

  const widthClass = size === "lg" ? "sm:max-w-2xl" : "sm:max-w-md";

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-end justify-center sm:items-center sm:p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
        onClick={() => onCloseRef.current?.()}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="client-dialog-title"
        className={`relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-2xl border border-cream-200 bg-surface-light shadow-2xl sm:max-h-[90vh] sm:rounded-2xl ${widthClass}`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-cream-200 px-6 pb-4 pt-5">
          <div className="min-w-0">
            <h3 id="client-dialog-title" className="truncate font-serif text-xl uppercase tracking-[0.12em] text-ink">
              {galleryTitle || heading}
            </h3>
            {photographerName && (
              <p className="mt-0.5 truncate text-[11px] uppercase tracking-[0.2em] text-muted">{photographerName}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => onCloseRef.current?.()}
            className="-mr-1.5 shrink-0 rounded-lg p-1.5 text-muted transition-colors hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
            aria-label="Close dialog"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>

        <div className="border-t border-cream-200 px-6 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-center text-[10px] uppercase tracking-[0.2em] text-muted">
          Powered by <span className="font-semibold text-ink">KYAPTURE</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
