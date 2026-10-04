import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import { useVisitorStore } from "../../store/visitorStore";

// 1R.6: the server never offers 'original' to a client (see
// apps/clients/download_access.py::resolution_is_allowed and
// DOWNLOAD_RESOLUTIONS in views.py) — "High Resolution" resolves, at
// serve time, to either the 3600px Download Master or a Pro
// photographer's chosen true original, but the word "Original" is
// never shown to a client.
const SIZE_OPTIONS = [
  { value: "download", label: "High Resolution", note: "Full quality, optimized for print and sharing" },
  { value: "web", label: "Web Size", note: "Small files, easy to share online" },
];
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPIRY_MARGIN_MS = 60 * 1000;

// Polling backoff while a gallery ZIP is prepared: check right away, then 2s,
// 5s, and every 10s after that, and give up after ten minutes (the job keeps
// running and, when we have an email, the client is emailed when it is ready).
const POLL_DELAYS_MS = [2000, 5000, 10000];
const POLL_GIVE_UP_MS = 10 * 60 * 1000;

function startBrowserDownload(href) {
  // No `download` attribute: the server's attachment header names the file, and
  // a cross-origin `download` name would be ignored anyway.
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function formatMegabytes(bytes) {
  const megabytes = (Number(bytes) || 0) / (1024 * 1024);
  return `${Math.max(0.1, megabytes).toFixed(1)} MB`;
}

function validityLabel(expiresAt) {
  const ms = expiresAt ? new Date(expiresAt).getTime() - Date.now() : 24 * 3600 * 1000;
  const hours = Math.max(0, Math.round(ms / 3600000));
  if (hours >= 1) return `Link valid for ${hours} ${hours === 1 ? "hour" : "hours"}`;
  return `Link valid for ${Math.max(1, Math.round(ms / 60000))} minutes`;
}

const heading = "font-serif text-xl uppercase tracking-[0.14em] text-ink";
const sectionLabel = "mb-3 font-serif text-base text-ink";
const primaryButton =
  "rounded-lg bg-ink px-8 py-3 text-xs font-medium uppercase tracking-[0.2em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-60";
const ghostButton = "rounded-lg px-4 py-2.5 text-sm text-muted transition hover:text-ink";

/**
 * Explicit download flow (the same component powers the in-gallery dialog and the
 * standalone /download page). Opening a gallery never reaches it — it exists only
 * once the visitor clicks Download.
 *
 *   form      ONE box. At the top, ONLY what this visitor still has to give:
 *               - an email   (the gallery requires one and this session has none yet)
 *               - the PIN    (the gallery has a download PIN and this session has not passed it)
 *             then scope + size, and a single Download button. Email and PIN are
 *             sent to the server together and checked there; a wrong PIN comes
 *             back inline as "Incorrect PIN". Once accepted, the signed access
 *             token is remembered for this browser session, so the next photo
 *             skips the details entirely. A gallery that needs neither goes
 *             straight to size choice / download.
 *   preparing a gallery/set ZIP is PREPARED in the background -> ready screen
 *             with a big Download button; a single photo downloads directly
 *
 * Closing the dialog never cancels a prepared download: the job keeps running,
 * and asking for the same download again simply picks it back up.
 */
export default function DownloadForm({
  username,
  slug,
  galleryToken = null,
  hasDownloadPin = false,
  downloadPolicy,
  target,
  photoSets = [],
  photoCount = 0,
  resumeJobId = null,
  linkExpired = false,
  onCancel,
}) {
  const uid = useId();
  const sessionKey = `${username}:${slug}`;
  const getDownloadAccess = useClientStore((state) => state.getDownloadAccess);
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);
  const profile = useVisitorStore((state) => state.profiles[sessionKey]);
  const setProfile = useVisitorStore((state) => state.setProfile);
  const policy = downloadPolicy || { allowed_sizes: ["download", "web"], require_email: true };
  const allowedSizes = useMemo(() => {
    const values = Array.isArray(policy.allowed_sizes) ? policy.allowed_sizes : [];
    const webPx = policy.web_px || 2048;
    const options = SIZE_OPTIONS.map((option) =>
      option.value === "web" ? { ...option, note: `${webPx} px — small files, easy to share online` } : option,
    );
    const allowed = options.filter((option) => values.includes(option.value));
    return allowed.length ? allowed : options;
  }, [policy.allowed_sizes, policy.web_px]);
  const requiresEmail = policy.require_email !== false;
  const isPhoto = target?.type === "photo";
  const defaultSize = (allowedSizes.find((option) => option.value === "download") || allowedSizes[0]).value;

  // 1R.6 "Photo Sets Available for Download": sets_enabled=null allows
  // the whole gallery and every set; once restricted to specific sets,
  // "All photos" is dropped entirely — the server refuses a
  // whole-gallery request the same way (set_is_enabled_for_download) —
  // and only the enabled sets are offered.
  const enabledSetIds = Array.isArray(policy.sets_enabled) ? policy.sets_enabled : null;
  const scopeOptions = useMemo(() => {
    if (!enabledSetIds) return [{ id: "", name: "All photos", photo_count: photoCount }, ...photoSets];
    return photoSets.filter((set) => enabledSetIds.includes(String(set.id)));
  }, [enabledSetIds, photoSets, photoCount]);

  // What the visitor still has to give. A remembered, unexpired access token
  // (earned earlier this session) covers both email and PIN.
  const storedAccess = useClientStore((state) => state.downloadAccess[sessionKey]);
  const rememberedAccess = storedAccess?.token && storedAccess.expiresAt > Date.now() ? storedAccess : null;
  const needsPin = hasDownloadPin && !rememberedAccess;
  const needsEmail = requiresEmail && !rememberedAccess;
  const needsGate = needsPin || needsEmail;

  const [step, setStep] = useState("form");
  const [scopeSetId, setScopeSetId] = useState(target?.type === "gallery" ? target.setId || "" : "");
  const [resolution, setResolution] = useState(defaultSize);
  const [email, setEmail] = useState(profile?.email || "");
  const [pin, setPin] = useState("");
  const pinInputRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState(linkExpired ? { form: "That download link has expired. Prepare your download again below." } : {});
  const [notifyEmail, setNotifyEmail] = useState(null);
  const [files, setFiles] = useState([]);
  const [expiresAt, setExpiresAt] = useState(null);
  const [failure, setFailure] = useState({ message: "", code: "" });
  const [startingFile, setStartingFile] = useState(null);
  const [startedFile, setStartedFile] = useState(null);

  const activeJob = useRef(null); // { id, access, startedAt }
  const pollTimer = useRef(null);
  const pollAttempt = useRef(0);
  const unmounted = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) window.clearTimeout(pollTimer.current);
    pollTimer.current = null;
  }, []);

  // If the active set was disabled for download (or the previously
  // browsed set is simply not in the enabled list), fall back to the
  // first option this visitor can actually choose.
  useEffect(() => {
    if (isPhoto) return;
    if (!scopeOptions.some((option) => option.id === scopeSetId)) {
      setScopeSetId(scopeOptions[0]?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeOptions, isPhoto]);

  useEffect(() => {
    unmounted.current = false;
    return () => {
      unmounted.current = true;
      stopPolling();
    };
  }, [stopPolling]);

  const failWith = useCallback(
    (message, code = "") => {
      stopPolling();
      if (unmounted.current) return;
      setFailure({ message, code });
      setStep("failed");
    },
    [stopPolling],
  );

  const sessionExpired = useCallback(() => {
    stopPolling();
    setDownloadAccess(sessionKey, null);
    setPin("");
    setErrors({ form: "Your download session expired. Please confirm your details again." });
    setStep("form");
  }, [sessionKey, setDownloadAccess, stopPolling]);

  const checkJob = useCallback(async () => {
    const job = activeJob.current;
    if (!job || unmounted.current) return;
    try {
      const status = await clientsApi.getDownloadJob(username, slug, job.id, {
        downloadToken: job.access?.token, token: galleryToken,
      });
      if (unmounted.current || activeJob.current !== job) return;
      if (status.state === "ready") {
        stopPolling();
        setFiles(status.files || []);
        setExpiresAt(status.expires_at || null);
        setStep("ready");
        return;
      }
      if (status.state === "failed") {
        failWith(status.error || "We couldn't prepare your photos. Please try again.", status.code || "");
        return;
      }
    } catch (err) {
      if (unmounted.current || activeJob.current !== job) return;
      if (err?.code === "download_access_expired") {
        sessionExpired();
        return;
      }
      if (err?.status === 404 || err?.status === 401 || err?.status === 403) {
        failWith(err.message || "We couldn't find this download. Please start it again.", err.code || "");
        return;
      }
      // Network hiccup / 5xx / throttle: keep trying on the same backoff.
    }
    if (Date.now() - job.startedAt > POLL_GIVE_UP_MS) {
      failWith("This is taking longer than expected. Please try again in a few minutes.");
      return;
    }
    const delay = POLL_DELAYS_MS[Math.min(pollAttempt.current, POLL_DELAYS_MS.length - 1)];
    pollAttempt.current += 1;
    pollTimer.current = window.setTimeout(checkJob, delay);
  }, [username, slug, galleryToken, stopPolling, failWith, sessionExpired]);

  const beginPolling = useCallback(
    (jobId, access) => {
      stopPolling();
      activeJob.current = { id: jobId, access, startedAt: Date.now() };
      pollAttempt.current = 0;
      setNotifyEmail(access?.email || null);
      setStep("preparing");
      checkJob();
    },
    [checkJob, stopPolling],
  );

  const prepareGallery = async (access = null) => {
    setErrors({});
    setFailure({ message: "", code: "" });
    setNotifyEmail(access?.email || null);
    setStep("preparing");
    try {
      const job = await clientsApi.prepareGalleryDownload(username, slug, {
        downloadToken: access?.token, token: galleryToken, resolution, setId: scopeSetId || undefined,
      });
      if (unmounted.current) return;
      beginPolling(job.job_id, access);
    } catch (err) {
      if (unmounted.current) return;
      if (err?.code === "download_access_expired") {
        sessionExpired();
      } else if (err?.status === 429) {
        failWith("Too many attempts. Please wait a minute and try again.");
      } else {
        failWith(err?.message || "We couldn't start preparing your photos. Please try again.");
      }
    }
  };

  const launchDownload = (access = null) => {
    if (!isPhoto) {
      prepareGallery(access);
      return;
    }
    const href = clientsApi.buildPhotoDownloadHref(target.photo?.download_url, {
      token: galleryToken, downloadToken: access?.token, resolution,
    });
    if (!href) {
      setErrors({ form: "This file isn't available for download." });
      setStep("form");
      return;
    }
    startBrowserDownload(href);
    setStep("requested");
  };

  // Arrived from the "ready" email: continue with that job as soon as access is in
  // hand — straight away when this session already has it, else after the details box.
  useEffect(() => {
    if (!resumeJobId || step !== "form" || needsGate) return;
    beginPolling(resumeJobId, getDownloadAccess(sessionKey));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeJobId, needsGate]);

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

  const finishWith = (access) => {
    if (resumeJobId) beginPolling(resumeJobId, access);
    else launchDownload(access);
  };

  const requestAccess = (credentials) =>
    clientsApi.requestDownloadAccess(username, slug, { ...credentials, token: galleryToken });

  const handleAuthorizationError = (err) => {
    if (err?.status === 429) {
      setErrors({ form: "Too many attempts. Please wait a minute and try again." });
    } else if (err?.code === "pin_required" || err?.code === "invalid_pin") {
      setPin("");
      setErrors({ pin: "Incorrect PIN" });
      requestAnimationFrame(() => pinInputRef.current?.focus());
    } else if (err?.code === "email_required" || err?.code === "invalid_email") {
      setErrors({ email: err.message });
    } else {
      setErrors({ form: err?.message || "Something went wrong. Please try again." });
    }
  };

  // The one submit: validate what is on screen, let the SERVER check email + PIN
  // together (so a wrong PIN is reported inline, before anything is prepared),
  // then start the download.
  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setErrors({});
    if (!needsGate) {
      finishWith(rememberedAccess);
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
      const grant = await requestAccess({
        email: needsEmail ? cleanEmail : undefined,
        pin: needsPin ? pin.trim() : undefined,
      });
      setPin("");
      finishWith(rememberAccess(grant, needsEmail ? cleanEmail : null));
    } catch (err) {
      handleAuthorizationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  // A ready file's signed link lives for the job's lifetime, but we still ask the
  // server at the moment of the click: if the job expired or its file vanished the
  // visitor gets "prepare again" instead of a dead link.
  const handleDownloadFile = async (file, index) => {
    const job = activeJob.current;
    if (!job || startingFile !== null) return;
    setStartingFile(index);
    setErrors({});
    try {
      const status = await clientsApi.getDownloadJob(username, slug, job.id, {
        downloadToken: job.access?.token, token: galleryToken,
      });
      if (status.state !== "ready") {
        failWith(status.error || "This download is no longer available.", status.code || "download_expired");
        return;
      }
      const fresh = status.files?.[index] || status.files?.find((entry) => entry.name === file.name);
      const href = clientsApi.buildJobFileHref(fresh?.url, { token: galleryToken });
      if (!href) {
        failWith("This download is no longer available.", "download_expired");
        return;
      }
      startBrowserDownload(href);
      setStartedFile(index);
    } catch (err) {
      if (err?.code === "download_access_expired") sessionExpired();
      else setErrors({ form: err?.message || "We couldn't start the download. Please try again." });
    } finally {
      if (!unmounted.current) setStartingFile(null);
    }
  };

  const inputClass = (hasError) =>
    `block w-full rounded-lg border px-3.5 py-3 text-sm text-ink bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${hasError ? "border-red-500" : "border-cream-300"}`;

  const spinner = (
    <svg className="h-7 w-7 animate-spin text-ink" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );

  // ── Single photo: the browser has been handed the file ─────────────────────
  if (step === "requested") {
    const sizeLabel = SIZE_OPTIONS.find((option) => option.value === resolution)?.label;
    const filename = target?.photo?.original_name || "photo";
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

  // ── 4a: preparing ─────────────────────────────────────────────────────────
  if (step === "preparing") {
    return (
      <div className="space-y-5 py-4 text-center" role="status" aria-live="polite">
        <div className="mx-auto flex h-14 w-14 items-center justify-center">{spinner}</div>
        <div>
          <h4 className={heading}>Preparing your download...</h4>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {notifyEmail
              ? "You will be notified by email once your download is ready. You can also stay on this page if you prefer."
              : "This can take a few minutes. You can stay on this page — your download will appear here when it is ready."}
          </p>
          <p className="mt-2 text-xs text-muted">Closing this window won&apos;t cancel it.</p>
        </div>
      </div>
    );
  }

  // ── 4b: ready ─────────────────────────────────────────────────────────────
  if (step === "ready") {
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border-2 border-brand-green-500 text-brand-green-600">
          <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
        </div>
        <h4 className={heading}>Your photos are ready to download</h4>
        <ul className="space-y-4">
          {files.map((file, index) => (
            <li key={file.name} className="space-y-3">
              <button
                type="button"
                onClick={() => handleDownloadFile(file, index)}
                disabled={startingFile !== null}
                className={primaryButton + " w-full !py-4 !text-sm"}
                aria-label={`Download ${file.name}`}
              >
                {startingFile === index ? "Starting…" : "Download"}
              </button>
              <p className="rounded-lg bg-cream-100 px-3 py-2.5 text-sm text-ink">
                <span className="block truncate" title={file.name}>{file.name}</span>
                <span className="text-xs text-muted">{formatMegabytes(file.size_bytes)}{startedFile === index ? " · downloading in your browser" : ""}</span>
              </p>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted">{validityLabel(expiresAt)}</p>
        {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
        {onCancel && <button type="button" onClick={onCancel} className={ghostButton}>Done</button>}
      </div>
    );
  }

  // ── failed / expired ──────────────────────────────────────────────────────
  if (step === "failed") {
    const expired = failure.code === "download_expired" || failure.code === "file_missing";
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div>
          <h4 className={heading}>{expired ? "This link has expired" : "We couldn't prepare your photos"}</h4>
          <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {expired ? "Link expired — prepare your download again to get a fresh one." : failure.message}
          </p>
        </div>
        <div className="flex justify-center gap-3">
          <button type="button" onClick={() => { setErrors({}); setStep("form"); }} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Back</button>
          <button type="button" onClick={() => prepareGallery(getDownloadAccess(sessionKey))} className={primaryButton + " !px-6 !py-2"}>{expired ? "Prepare again" : "Try again"}</button>
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

      {!resumeJobId && (
        <>
          {!isPhoto && (
            <fieldset>
              <legend className={sectionLabel}>Choose Photos</legend>
              <div className="space-y-2">
                {scopeOptions.map((option) => (
                  <label key={option.id || "all"} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-1 py-1.5 text-sm text-ink">
                    <span className="flex items-center gap-3">
                      <input type="radio" name={`${uid}-scope`} checked={scopeSetId === option.id} onChange={() => setScopeSetId(option.id)} className="h-4 w-4 accent-ink" />
                      {option.name}
                    </span>
                    <span className="text-xs text-muted">{option.photo_count ?? 0} photos</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {isPhoto && <p className="truncate text-sm text-muted" title={target.photo?.original_name}>{target.photo?.original_name || "This photo"}</p>}

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
        </>
      )}

      {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
      {/* In the dialog the action row stays pinned to the bottom of the scrolling body, so the Download button is always in reach. */}
      <div className={`flex justify-center gap-2 ${onCancel ? "sticky bottom-0 -mx-6 -mb-5 border-t border-cream-200 bg-surface-light px-6 py-4" : "pt-1"}`}>
        {onCancel && <button type="button" onClick={onCancel} className={ghostButton}>Cancel</button>}
        <button type="submit" disabled={submitting} className={primaryButton}>{submitting ? "Checking…" : "Download"}</button>
      </div>
    </form>
  );
}
