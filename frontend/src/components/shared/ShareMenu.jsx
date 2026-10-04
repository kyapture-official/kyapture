// File Location: frontend/src/components/shared/ShareMenu.jsx
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link2, Mail, QrCode, Share2 } from "lucide-react";
import ShareLinkModal from "./ShareLinkModal";
import ShareQrModal from "./ShareQrModal";
import { useToast } from "../ui/Toast";
import { buildShareEmailHref, canNativeShare, shareText, toCanonicalShareUrl } from "../../utils/share";

/**
 * Share a gallery — a deliberately small dropdown (Pixieset style):
 *
 *   Share by email   opens the visitor's mail app with the title and link filled in
 *   Get direct link  opens the link modal (link field + Copy / "Copied")
 *   Get QR code      opens the QR modal (QR + Download PNG)
 *   Share…           the device's native share sheet — ONLY where `navigator.share`
 *                    exists. It already lists every installed app, so there are no
 *                    separate WhatsApp / Facebook / Messenger / Copy buttons.
 *
 * The URL shared is always the plain, credential-free gallery link (see
 * utils/share.js) — sharing never carries or grants access; the gallery's own
 * password / published / expiry gates apply to whoever opens it.
 *
 * Layout: a popover under the trigger on larger screens, a bottom sheet on
 * phones. Keyboard: Escape closes (focus returns to the trigger), Up/Down/Home/
 * End move between options, Tab stays inside the menu while it's open.
 *
 * variant="icon"   → the compact toolbar icon button (client gallery)
 * variant="button" → a labelled button (photographer dashboard)
 */
export default function ShareMenu({ url, title, variant = "icon", note = null, align = "right" }) {
  const toast = useToast();
  const menuId = useId();
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState(null); // null | "link" | "qr"

  const shareUrl = toCanonicalShareUrl(url);
  const nativeShare = canNativeShare();

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  // Outside click / tap closes; so does Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (menuRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return;
      close(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close(true);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [open, close]);

  // Move focus into the menu when it opens.
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => menuRef.current?.querySelector('[role="menuitem"]')?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const items = () => Array.from(menuRef.current?.querySelectorAll('[role="menuitem"]') || []);

  const handleMenuKeyDown = (event) => {
    const list = items();
    if (!list.length) return;
    const index = list.indexOf(document.activeElement);
    let next = null;
    if (event.key === "ArrowDown") next = list[(index + 1) % list.length];
    else if (event.key === "ArrowUp") next = list[(index - 1 + list.length) % list.length];
    else if (event.key === "Home") next = list[0];
    else if (event.key === "End") next = list[list.length - 1];
    else if (event.key === "Tab") {
      // Keep focus inside the open menu.
      event.preventDefault();
      next = event.shiftKey ? list[(index - 1 + list.length) % list.length] : list[(index + 1) % list.length];
    }
    if (next) {
      event.preventDefault();
      next.focus();
    }
  };

  const handleNative = async () => {
    try {
      await navigator.share({ title: title || undefined, text: shareText(title), url: shareUrl });
      close();
    } catch (err) {
      // The user dismissing the sheet is not an error.
      if (err?.name !== "AbortError") toast("Sharing isn't available right now.", "error");
    }
  };

  // The menu closes WITHOUT stealing focus back, so the dialog it opens keeps it.
  const openDialog = (name) => {
    close(false);
    setDialog(name);
  };

  if (!shareUrl) return null;

  const itemClass =
    "flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-ink transition-colors hover:bg-cream-100 focus:bg-cream-100 focus:outline-none sm:px-3 sm:py-2.5 sm:text-xs";
  // A plain function returning an element (NOT a component): a component
  // defined inside render would remount on every render and drop keyboard focus.
  const menuItem = (Icon, label, onClick) => (
    <button key={label} type="button" role="menuitem" onClick={onClick} className={itemClass}>
      <Icon className="h-4 w-4 flex-shrink-0 text-muted" aria-hidden="true" />
      {label}
    </button>
  );

  const menuLink = (Icon, label, href) => (
    <a key={label} role="menuitem" href={href} onClick={() => close(false)} className={itemClass}>
      <Icon className="h-4 w-4 flex-shrink-0 text-muted" aria-hidden="true" />
      {label}
    </a>
  );

  const trigger =
    variant === "button" ? (
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-cream-200 bg-surface-light px-3 py-2 text-xs font-medium text-ink/80 shadow-sm transition-all hover:bg-cream-100 hover:text-ink hover:shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
      >
        <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
        Share
      </button>
    ) : (
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label="Share gallery"
        title="Share"
        className="rounded p-2 text-slate-600 transition hover:bg-slate-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
      >
        <Share2 className="h-5 w-5" />
      </button>
    );

  return (
    <div className="relative">
      {trigger}
      <ShareLinkModal open={dialog === "link"} onClose={() => setDialog(null)} url={shareUrl} note={note} />
      <ShareQrModal open={dialog === "qr"} onClose={() => setDialog(null)} url={shareUrl} filename={shareUrl.split("/").pop()} />
      {open && (
        <>
          {/* Phones: dim the page behind the bottom sheet */}
          <div className="fixed inset-0 z-40 bg-black/30 sm:hidden" aria-hidden="true" />
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label="Share this gallery"
            onKeyDown={handleMenuKeyDown}
            className={`fixed inset-x-0 bottom-0 z-50 overflow-hidden rounded-t-2xl border border-cream-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-2xl sm:absolute sm:inset-x-auto sm:bottom-auto sm:top-full sm:mt-2 sm:w-64 sm:rounded-xl sm:pb-0 sm:shadow-card ${
              align === "left" ? "sm:left-0" : "sm:right-0"
            }`}
          >
            <p className="border-b border-cream-200 px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-muted sm:px-3 sm:py-2">
              Share this gallery
            </p>
            {note && <p className="border-b border-cream-200 bg-amber-50 px-4 py-2 text-[11px] leading-snug text-amber-800 sm:px-3">{note}</p>}

            <div className="py-1">
              {menuLink(Mail, "Share by email", buildShareEmailHref({ url: shareUrl, title }))}
              {menuItem(Link2, "Get direct link", () => openDialog("link"))}
              {menuItem(QrCode, "Get QR code", () => openDialog("qr"))}
              {nativeShare && menuItem(Share2, "Share…", handleNative)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
