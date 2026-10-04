// File Location: frontend/src/components/shared/ShareLinkModal.jsx
import { useEffect, useRef, useState } from "react";
import Modal from "../ui/Modal";
import { copyText } from "../../utils/share";

const COPIED_MS = 2000;

/**
 * "Get direct link": the gallery link in a read-only field with a Copy button
 * that flips to "Copied". The ONE link modal — the Share dropdown and the
 * collection's three-dot menu both open this same component.
 *
 * If the browser refuses to copy (no clipboard permission, plain http), the
 * button says so honestly and the link stays selected, ready for Ctrl/Cmd+C.
 */
export default function ShareLinkModal({ open, onClose, url, note = null }) {
  const inputRef = useRef(null);
  const timerRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | copied | failed

  useEffect(() => {
    if (!open) setStatus("idle");
    return () => window.clearTimeout(timerRef.current);
  }, [open]);

  const handleCopy = async () => {
    window.clearTimeout(timerRef.current);
    const ok = await copyText(url);
    setStatus(ok ? "copied" : "failed");
    if (ok) {
      timerRef.current = window.setTimeout(() => setStatus("idle"), COPIED_MS);
    } else {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Direct link" size="sm">
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-muted">
          Anyone with this link can open the collection. Its publish and password settings still apply.
        </p>
        {note && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-snug text-amber-800">{note}</p>}
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            ref={inputRef}
            readOnly
            value={url}
            aria-label="Direct link"
            onFocus={(event) => event.target.select()}
            className="min-w-0 flex-1 rounded-lg border border-cream-200 bg-cream-100/50 px-3 py-2.5 font-mono text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand-green-500"
          />
          <button
            type="button"
            onClick={handleCopy}
            className="rounded-lg bg-ink px-5 py-2.5 text-xs font-medium uppercase tracking-[0.15em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 sm:min-w-[6.5rem]"
          >
            {status === "copied" ? "Copied" : "Copy"}
          </button>
        </div>
        <p role="status" aria-live="polite" className="min-h-[1rem] text-xs text-muted">
          {status === "copied" && "Link copied to your clipboard."}
          {status === "failed" && "Couldn't copy automatically — the link is selected, press Ctrl/Cmd+C."}
        </p>
      </div>
    </Modal>
  );
}
