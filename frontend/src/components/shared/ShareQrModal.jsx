// File Location: frontend/src/components/shared/ShareQrModal.jsx
import { useEffect, useState } from "react";
import Modal from "../ui/Modal";

const QR_PIXELS = 768; // PNG size: crisp on print, still small

/**
 * "Get QR code": the gallery link as a QR code with a Download PNG button.
 * The QR library is loaded only when this modal is first opened, so it is not
 * part of the gallery's initial bundle.
 */
export default function ShareQrModal({ open, onClose, url, filename = "gallery" }) {
  const [state, setState] = useState({ status: "idle", dataUrl: "" }); // idle | loading | ready | error

  useEffect(() => {
    if (!open || !url) return undefined;
    let cancelled = false;
    setState({ status: "loading", dataUrl: "" });
    import("qrcode")
      .then((module) => (module.default || module).toDataURL(url, { width: QR_PIXELS, margin: 2, errorCorrectionLevel: "M" }))
      .then((dataUrl) => {
        if (!cancelled) setState({ status: "ready", dataUrl });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", dataUrl: "" });
      });
    return () => {
      cancelled = true;
    };
  }, [open, url]);

  const safeName = String(filename || "gallery").replace(/[^a-z0-9-_]+/gi, "-").replace(/^-+|-+$/g, "") || "gallery";

  return (
    <Modal open={open} onClose={onClose} title="QR code" size="sm">
      <div className="space-y-4 text-center">
        <p className="text-sm leading-relaxed text-muted">Scan with a phone camera to open the collection.</p>
        <div className="mx-auto flex h-60 w-60 items-center justify-center rounded-xl border border-cream-200 bg-white p-2">
          {state.status === "ready" && (
            <img src={state.dataUrl} alt="QR code for the collection link" className="h-full w-full" />
          )}
          {state.status === "loading" && <span className="text-xs text-muted">Generating…</span>}
          {state.status === "error" && (
            <span role="alert" className="px-3 text-xs text-red-700">Couldn&apos;t create the QR code. Close this and try again.</span>
          )}
        </div>
        <p className="truncate text-[11px] text-muted" title={url}>{url}</p>
        <a
          href={state.status === "ready" ? state.dataUrl : undefined}
          download={`${safeName}-qr.png`}
          aria-disabled={state.status !== "ready"}
          onClick={(event) => {
            if (state.status !== "ready") event.preventDefault();
          }}
          className={`inline-block rounded-lg bg-ink px-6 py-2.5 text-xs font-medium uppercase tracking-[0.15em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
            state.status !== "ready" ? "pointer-events-none opacity-50" : ""
          }`}
        >
          Download PNG
        </a>
      </div>
    </Modal>
  );
}
