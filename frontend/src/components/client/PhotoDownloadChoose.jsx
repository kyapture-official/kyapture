import { useId, useMemo, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import {
  blockedMessage, defaultSize, isBlockedCode, photoPrefsKey, photoSizeOptions, readRememberedSize,
  writeRememberedSize,
} from "../../utils/downloadFlow.js";
import { pageButtonClass } from "./DownloadShell";

const sectionLabel = "mb-3 text-xs uppercase tracking-[0.22em] text-muted";
const optionClass = (active) =>
  `relative flex w-full items-center justify-center border px-4 py-4 text-[15px] text-ink transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${active ? "border-ink" : "border-cream-300 hover:border-ink/50"}`;

const CheckIcon = ({ className = "h-4 w-4" }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
);

/**
 * Single photo — "DOWNLOAD PHOTO": PHOTO SIZE (only the sizes the photographer
 * enabled), DOWNLOAD TO (this device only), "Remember my selection" and the
 * button. The button asks the server first (?check=1: every gate, nothing served
 * or logged) and only then hands the browser the file as a plain link, so the
 * file arrives as a DIRECT download with its real name — no ZIP, no preparing
 * page — and a refusal is shown here instead of replacing the gallery tab.
 */
export default function PhotoDownloadChoose({
  username, slug, galleryToken = null, policy, studio, photo, access = null, onDone, onNeedAccess,
}) {
  const uid = useId();
  const prefsKey = photoPrefsKey(username, slug);
  const options = useMemo(() => photoSizeOptions(policy), [policy]);
  const storage = typeof window === "undefined" ? null : window.localStorage;
  const [remembered] = useState(() => readRememberedSize(storage, prefsKey, options));
  const [resolution, setResolution] = useState(() => remembered || defaultSize(options));
  const [remember, setRemember] = useState(Boolean(remembered));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const limitReached = Boolean(policy?.limit_reached);

  const startDownload = (href) => {
    // No `download` attribute: the server's attachment header names the file.
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy || limitReached) return;
    setBusy(true);
    setError("");
    const opts = { token: galleryToken, downloadToken: access?.token, resolution };
    try {
      await clientsApi.checkPhotoDownload(photo.download_url, opts);
    } catch (err) {
      setBusy(false);
      if (err?.code === "download_access_expired" || err?.code === "download_access_required") {
        onNeedAccess?.("Your download session has expired. Please confirm your details again.");
      } else if (isBlockedCode(err?.code)) {
        setError(blockedMessage(err.code, studio, err.message));
      } else if (err?.code === "resolution_not_allowed") {
        setError("That size is no longer available. Please choose another.");
      } else {
        setError(err?.message || "Something went wrong. Please try again.");
      }
      return;
    }
    const href = clientsApi.buildPhotoDownloadHref(photo.download_url, opts);
    writeRememberedSize(storage, prefsKey, resolution, remember);
    startDownload(href);
    onDone?.();
  };

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-8 text-left">
      <h2 className="font-serif text-xl font-bold uppercase tracking-[0.16em] text-ink">Download Photo</h2>

      <fieldset>
        <legend className={sectionLabel}>Photo Size</legend>
        <div className="space-y-2" role="radiogroup" aria-label="Photo size">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={resolution === option.value}
              onClick={() => { setResolution(option.value); setError(""); }}
              className={optionClass(resolution === option.value)}
            >
              {resolution === option.value && <CheckIcon className="absolute left-5 h-4 w-4" />}
              <span>
                {option.label}
                {option.note && <span className="ml-2 text-xs text-muted">{option.note}</span>}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <p className={sectionLabel}>Download To</p>
        <div className={optionClass(true) + " gap-3"}>
          <CheckIcon className="absolute left-5 h-4 w-4" />
          <svg className="h-5 w-5 shrink-0 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h12a2 2 0 012 2v9H4V6zm-2 11h20v1a2 2 0 01-2 2H4a2 2 0 01-2-2v-1z" /></svg>
          Save to My Device
        </div>
      </div>

      <label htmlFor={`${uid}-remember`} className="flex cursor-pointer items-center justify-center gap-2 text-sm text-ink">
        <input
          id={`${uid}-remember`}
          type="checkbox"
          checked={remember}
          onChange={(event) => setRemember(event.target.checked)}
          className="h-4 w-4 cursor-pointer accent-ink"
        />
        Remember my selection
      </label>

      {(limitReached || error) && (
        <p role="alert" className="bg-red-50 px-3 py-2 text-sm text-red-700">
          {limitReached ? blockedMessage("download_limit_reached", studio) : error}
        </p>
      )}

      <button type="submit" disabled={busy || limitReached} className={`${pageButtonClass} !w-full`}>
        {busy ? "Starting…" : "Download Photo"}
      </button>
    </form>
  );
}
