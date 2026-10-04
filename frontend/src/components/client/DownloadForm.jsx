import { useEffect, useId, useMemo, useRef, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import { useVisitorStore } from "../../store/visitorStore";
import { EMAIL_PATTERN, SIZE_OPTIONS } from "../../utils/downloadFlow.js";

const EXPIRY_MARGIN_MS = 60 * 1000;

const heading = "font-serif text-xl uppercase tracking-[0.14em] text-ink";
const sectionLabel = "mb-3 font-serif text-base text-ink";
const primaryButton =
  "rounded-lg bg-ink px-8 py-3 text-xs font-medium uppercase tracking-[0.2em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-60";
const ghostButton = "rounded-lg px-4 py-2.5 text-sm text-muted transition hover:text-ink";

/**
 * Single-photo download (the photo tile / lightbox Download button, in
 * DownloadModal). A gallery or set download is a full page instead — see
 * pages/client/DownloadPage.jsx.
 *
 * ONE box. At the top, ONLY what this visitor still has to give:
 *   - an email   (the gallery requires one and this session has none yet)
 *   - the PIN    (the gallery has a download PIN and this session has not passed it)
 * then the size and a single Download button. Email and PIN go to the server
 * together and are checked there; a wrong PIN comes back inline as "Incorrect
 * PIN". Once accepted, the signed access token is remembered for this browser
 * session, so the next photo skips the details. The browser then downloads the
 * file directly.
 */
export default function DownloadForm({
  username,
  slug,
  galleryToken = null,
  hasDownloadPin = false,
  downloadPolicy,
  photo,
  onCancel,
}) {
  const uid = useId();
  const sessionKey = `${username}:${slug}`;
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);
  const profile = useVisitorStore((state) => state.profiles[sessionKey]);
  const setProfile = useVisitorStore((state) => state.setProfile);
  const policy = downloadPolicy || { allowed_sizes: ["download", "web"], require_email: true };
  const allowedSizes = useMemo(() => {
    const values = Array.isArray(policy.allowed_sizes) ? policy.allowed_sizes : [];
    const webPx = policy.web_px || 2048;
    const options = [
      { ...SIZE_OPTIONS[0], note: "Full quality, optimized for print and sharing" },
      { ...SIZE_OPTIONS[1], note: `${webPx} px — small files, easy to share online` },
    ];
    const allowed = options.filter((option) => values.includes(option.value));
    return allowed.length ? allowed : options;
  }, [policy.allowed_sizes, policy.web_px]);
  const requiresEmail = policy.require_email !== false;
  const defaultSize = (allowedSizes.find((option) => option.value === "download") || allowedSizes[0]).value;

  // What the visitor still has to give. A remembered, unexpired access token
  // (earned earlier this session) covers both email and PIN.
  const storedAccess = useClientStore((state) => state.downloadAccess[sessionKey]);
  const rememberedAccess = storedAccess?.token && storedAccess.expiresAt > Date.now() ? storedAccess : null;
  const needsPin = hasDownloadPin && !rememberedAccess;
  const needsEmail = requiresEmail && !rememberedAccess;
  const needsGate = needsPin || needsEmail;

  const [step, setStep] = useState("form");
  const [resolution, setResolution] = useState(defaultSize);
  const [email, setEmail] = useState(profile?.email || "");
  const [pin, setPin] = useState("");
  const pinInputRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const unmounted = useRef(false);

  useEffect(() => {
    unmounted.current = false;
    return () => {
      unmounted.current = true;
    };
  }, []);

  const launchDownload = (access = null) => {
    const href = clientsApi.buildPhotoDownloadHref(photo?.download_url, {
      token: galleryToken, downloadToken: access?.token, resolution,
    });
    if (!href) {
      setErrors({ form: "This file isn't available for download." });
      setStep("form");
      return;
    }
    // No `download` attribute: the server's attachment header names the file.
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setStep("requested");
  };

  const rememberAccess = (grant, fallbackEmail) => {
    const access = {
      token: grant.download_token,
      email: grant.email || fallbackEmail || null,
      expiresAt: Date.now() + Math.max(0, (grant.expires_in || 0) * 1000 - EXPIRY_MARGIN_MS),
    };
    setDownloadAccess(sessionKey, access);
    if (access.email) setProfile(sessionKey, { email: access.email, name: profile?.name || "" });
    return access;
  };

  const handleAuthorizationError = (err) => {
    if (err?.status === 429) {
      setErrors({ form: "Too many attempts. Please wait a minute and try again." });
    } else if (err?.code === "pin_required" || err?.code === "invalid_pin") {
      setPin("");
      setErrors({ pin: "Incorrect PIN" });
      requestAnimationFrame(() => pinInputRef.current?.focus());
    } else if (err?.code === "email_required" || err?.code === "invalid_email" || err?.code === "email_not_authorized") {
      setErrors({ email: err.message });
    } else {
      setErrors({ form: err?.message || "Something went wrong. Please try again." });
    }
  };

  // The one submit: validate what is on screen, let the SERVER check email + PIN
  // together (so a wrong PIN is reported inline), then start the download.
  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setErrors({});
    if (!needsGate) {
      launchDownload(rememberedAccess);
      return;
    }
    const cleanEmail = email.trim();
    const problems = {};
    if (needsEmail && !EMAIL_PATTERN.test(cleanEmail)) problems.email = "Please enter a valid email address.";
    if (needsPin && !pin.trim()) problems.pin = "Enter the download PIN.";
    if (Object.keys(problems).length) {
      setErrors(problems);
      return;
    }
    setSubmitting(true);
    try {
      const grant = await clientsApi.requestDownloadAccess(username, slug, {
        email: needsEmail ? cleanEmail : undefined,
        pin: needsPin ? pin.trim() : undefined,
        token: galleryToken,
      });
      setPin("");
      launchDownload(rememberAccess(grant, needsEmail ? cleanEmail : null));
    } catch (err) {
      handleAuthorizationError(err);
    } finally {
      if (!unmounted.current) setSubmitting(false);
    }
  };

  const inputClass = (hasError) =>
    `block w-full rounded-lg border px-3.5 py-3 text-sm text-ink bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${hasError ? "border-red-500" : "border-cream-300"}`;

  // ── the browser has been handed the file ───────────────────────────────────
  if (step === "requested") {
    const sizeLabel = SIZE_OPTIONS.find((option) => option.value === resolution)?.label;
    const filename = photo?.original_name || "photo";
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
          <svg className="h-6 w-6 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
        </div>
        <div>
          <h4 className={heading}>Your download was requested</h4>
          <p className="mt-2 text-sm leading-relaxed text-muted">Your browser is downloading the selected photo.</p>
        </div>
        <p className="truncate rounded-lg bg-cream-100 px-3 py-2 text-xs text-muted" title={filename}>{filename} · {sizeLabel}</p>
        <div className="flex justify-center gap-3">
          <button type="button" onClick={() => setStep("form")} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Download again</button>
          {onCancel && <button type="button" onClick={onCancel} className={primaryButton + " !px-6 !py-2"}>Done</button>}
        </div>
      </div>
    );
  }

  // ── the one box ───────────────────────────────────────────────────────────
  const gateIntro =
    needsEmail && needsPin
      ? "Your email will be used to notify you when the files are ready for download. Please enter the download PIN provided by your photographer to download this photo collection."
      : needsPin
        ? "Please enter the download PIN provided by your photographer to download this photo collection."
        : "Your email will be used to notify you when the files are ready for download.";
  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-7 text-left">
      {needsGate && (
        <section className="space-y-4" aria-label="Your details">
          <p className="text-sm leading-relaxed text-muted">{gateIntro}</p>
          {needsEmail && (
            <div className="space-y-1.5">
              <label htmlFor={`${uid}-email`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Email address</label>
              <input
                id={`${uid}-email`}
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(event) => { setEmail(event.target.value); if (errors.email) setErrors({}); }}
                placeholder="you@email.com"
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? `${uid}-email-error` : undefined}
                className={inputClass(errors.email)}
              />
              {errors.email && <p id={`${uid}-email-error`} role="alert" className="text-xs text-red-600">{errors.email}</p>}
              <p className="text-[11px] leading-relaxed text-muted">By continuing, you agree that your email is shared with the photographer so they know who downloaded their photos. We&apos;ll remember it on this device.</p>
            </div>
          )}
          {needsPin && (
            <div className="space-y-1.5">
              <label htmlFor={`${uid}-pin`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Download PIN</label>
              <input
                id={`${uid}-pin`}
                ref={pinInputRef}
                type="password"
                inputMode="numeric"
                autoComplete="off"
                autoFocus={!needsEmail}
                maxLength={8}
                value={pin}
                onChange={(event) => { setPin(event.target.value.replace(/\D/g, "")); if (errors.pin) setErrors({}); }}
                placeholder="Enter download PIN"
                aria-invalid={Boolean(errors.pin)}
                aria-describedby={errors.pin ? `${uid}-pin-error` : undefined}
                className={inputClass(errors.pin)}
              />
              {errors.pin && <p id={`${uid}-pin-error`} role="alert" className="text-xs text-red-600">{errors.pin}</p>}
            </div>
          )}
        </section>
      )}

      <p className="truncate text-sm text-muted" title={photo?.original_name}>{photo?.original_name || "This photo"}</p>

      <fieldset>
        <legend className={sectionLabel}>Choose Download Size</legend>
        <div className="space-y-2.5">
          {allowedSizes.map((option) => (
            <label key={option.value} className="flex cursor-pointer items-start gap-3 rounded-lg px-1 py-1.5">
              <input type="radio" name={`${uid}-resolution`} value={option.value} checked={resolution === option.value} onChange={() => setResolution(option.value)} className="mt-1 h-4 w-4 accent-ink" />
              <span>
                <span className="block text-sm text-ink">{option.label}</span>
                <span className="block text-xs text-muted">{option.note}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <p className={sectionLabel}>Download To</p>
        <div className="flex items-center justify-center gap-3 rounded-lg border border-cream-300 bg-white px-4 py-3.5 text-sm text-ink">
          <svg className="h-5 w-5 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h12a2 2 0 012 2v9H4V6zm-2 11h20v1a2 2 0 01-2 2H4a2 2 0 01-2-2v-1z" /></svg>
          Save to My Device
          <svg className="h-4 w-4 text-brand-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
        </div>
      </div>

      {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
      {/* The action row stays pinned to the bottom of the scrolling dialog body, so the Download button is always in reach. */}
      <div className="sticky bottom-0 -mx-6 -mb-5 flex justify-center gap-2 border-t border-cream-200 bg-surface-light px-6 py-4">
        {onCancel && <button type="button" onClick={onCancel} className={ghostButton}>Cancel</button>}
        <button type="submit" disabled={submitting} className={primaryButton}>{submitting ? "Checking…" : "Download"}</button>
      </div>
    </form>
  );
}
