import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";

const SIZE_OPTIONS = [
  { value: "download", label: "High Resolution", hint: "Full-quality photos" },
  { value: "web", label: "Web Size", hint: "Smaller files, easy to share" },
];
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPIRY_MARGIN_MS = 60 * 1000;

// Polling backoff while a gallery ZIP is prepared: check right away, then 2s,
// 5s, and every 10s after that, and give up after ten minutes (the job keeps
// running and, when we have an email, the client is emailed when it is ready).
const POLL_DELAYS_MS = [2000, 5000, 10000];
const POLL_GIVE_UP_MS = 10 * 60 * 1000;

function startBrowserDownload(href, filename) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.rel = "noopener";
  anchor.download = filename || "";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function formatMegabytes(bytes) {
  const megabytes = (Number(bytes) || 0) / (1024 * 1024);
  return `${Math.max(0.1, megabytes).toFixed(1)} MB`;
}

/**
 * Explicit download flow.
 *
 *   photo    choose size -> (email/PIN when required) -> the browser downloads it
 *   gallery  choose scope + size -> (email/PIN when required) -> the server
 *            PREPARES the ZIP in the background ("preparing") -> "ready" with
 *            the file name and size -> click to download
 *
 * Gallery ZIPs are never streamed straight from a click: the server answers
 * with a job, this form polls it, and the final browser download uses a
 * short-lived signed link fetched at the moment of the click.
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
  onCancel,
}) {
  const uid = useId();
  const sessionKey = `${username}:${slug}`;
  const getDownloadAccess = useClientStore((state) => state.getDownloadAccess);
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);
  const storedAccess = useClientStore((state) => state.downloadAccess[sessionKey]);
  const policy = downloadPolicy || { allowed_sizes: ["download", "web"], require_email: true };
  const allowedSizes = useMemo(() => {
    const values = Array.isArray(policy.allowed_sizes) ? policy.allowed_sizes : [];
    const allowed = SIZE_OPTIONS.filter((option) => values.includes(option.value));
    return allowed.length ? allowed : SIZE_OPTIONS;
  }, [policy.allowed_sizes]);
  const requiresEmail = policy.require_email !== false;
  const requiresAccess = requiresEmail || hasDownloadPin;
  const isPhoto = target?.type === "photo";

  // "resume" = arrived from the "your photos are ready" email: skip choosing
  // and go straight to that job once the visitor has re-verified.
  const [step, setStep] = useState(resumeJobId && requiresAccess && !getDownloadAccess(sessionKey) ? "identity" : "choose");
  const [scopeSetId, setScopeSetId] = useState(target?.type === "gallery" ? target.setId || "" : "");
  const [resolution, setResolution] = useState(allowedSizes[0].value);
  const [email, setEmail] = useState(storedAccess?.email || "");
  const [pin, setPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [notifyEmail, setNotifyEmail] = useState(null);
  const [files, setFiles] = useState([]);
  const [failure, setFailure] = useState("");
  const [startingFile, setStartingFile] = useState(null);
  const [startedFile, setStartedFile] = useState(null);

  const activeJob = useRef(null); // { id, access, startedAt }
  const pollTimer = useRef(null);
  const pollAttempt = useRef(0);
  const unmounted = useRef(false);
  const selectedSet = photoSets.find((set) => set.id === scopeSetId) || null;

  const stopPolling = useCallback(() => {
    if (pollTimer.current) window.clearTimeout(pollTimer.current);
    pollTimer.current = null;
  }, []);

  useEffect(() => {
    unmounted.current = false;
    return () => {
      unmounted.current = true;
      stopPolling();
    };
  }, [stopPolling]);

  const failWith = useCallback((message) => {
    stopPolling();
    if (unmounted.current) return;
    setFailure(message);
    setStep("failed");
  }, [stopPolling]);

  const sessionExpired = useCallback(() => {
    stopPolling();
    setDownloadAccess(sessionKey, null);
    setPin("");
    setErrors({ form: "Your download session expired. Please confirm your details again." });
    setStep("identity");
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
        setStep("ready");
        return;
      }
      if (status.state === "failed") {
        failWith(status.error || "We couldn't prepare your photos. Please try again.");
        return;
      }
    } catch (err) {
      if (unmounted.current || activeJob.current !== job) return;
      if (err?.code === "download_access_expired") {
        sessionExpired();
        return;
      }
      if (err?.status === 404 || err?.status === 401 || err?.status === 403) {
        failWith(err.message || "We couldn't find this download. Please start it again.");
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

  const beginPolling = useCallback((jobId, access) => {
    stopPolling();
    activeJob.current = { id: jobId, access, startedAt: Date.now() };
    pollAttempt.current = 0;
    setNotifyEmail(access?.email || null);
    setStep("preparing");
    checkJob();
  }, [checkJob, stopPolling]);

  const prepareGallery = async (access = null) => {
    setErrors({});
    setFailure("");
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
      return;
    }
    startBrowserDownload(href, target.photo?.original_name || "photo");
    setStep("requested");
  };

  // Arrived from the "ready" email: continue with that job as soon as access is in hand.
  useEffect(() => {
    if (!resumeJobId || step !== "choose") return;
    beginPolling(resumeJobId, getDownloadAccess(sessionKey));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeJobId]);

  const handleChoose = (event) => {
    event.preventDefault();
    setErrors({});
    const rememberedAccess = getDownloadAccess(sessionKey);
    if (!requiresAccess || rememberedAccess) {
      launchDownload(rememberedAccess);
      return;
    }
    setStep("identity");
  };

  const handleAuthorizationError = (err) => {
    if (err?.status === 429) {
      setErrors({ form: "Too many attempts. Please wait a minute and try again." });
    } else if (err?.code === "pin_required" || err?.code === "invalid_pin") {
      setPin("");
      setErrors({ pin: err.message });
    } else if (err?.code === "email_required" || err?.code === "invalid_email") {
      setErrors({ email: err.message });
    } else {
      setErrors({ form: err?.message || "Something went wrong. Please try again." });
    }
  };

  const handleIdentity = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setErrors({});
    const cleanEmail = email.trim();
    if (requiresEmail && !EMAIL_PATTERN.test(cleanEmail)) {
      setErrors({ email: "Please enter a valid email address." });
      return;
    }
    if (hasDownloadPin && !pin.trim()) {
      setErrors({ pin: "Enter the download PIN your photographer gave you." });
      return;
    }
    setSubmitting(true);
    try {
      const grant = await clientsApi.requestDownloadAccess(username, slug, {
        email: requiresEmail ? cleanEmail : undefined,
        pin: hasDownloadPin ? pin.trim() : undefined,
        token: galleryToken,
      });
      const access = {
        token: grant.download_token,
        email: grant.email || cleanEmail || null,
        expiresAt: Date.now() + Math.max(0, (grant.expires_in || 0) * 1000 - EXPIRY_MARGIN_MS),
      };
      setDownloadAccess(sessionKey, access);
      setPin("");
      if (resumeJobId) beginPolling(resumeJobId, access);
      else launchDownload(access);
    } catch (err) {
      handleAuthorizationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  // A ready file's signed link only lives a few minutes, so ask for a fresh
  // one at the moment of the click instead of trusting the one we listed.
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
        failWith(status.error || "This download is no longer available. Please start it again.");
        return;
      }
      const fresh = status.files?.[index] || status.files?.find((entry) => entry.name === file.name);
      const href = clientsApi.buildJobFileHref(fresh?.url, { token: galleryToken });
      if (!href) {
        failWith("This download is no longer available. Please start it again.");
        return;
      }
      startBrowserDownload(href, fresh.name);
      setStartedFile(index);
    } catch (err) {
      if (err?.code === "download_access_expired") sessionExpired();
      else setErrors({ form: err?.message || "We couldn't start the download. Please try again." });
    } finally {
      if (!unmounted.current) setStartingFile(null);
    }
  };

  const inputClass = (hasError) =>
    `block w-full rounded-lg border px-3.5 py-2.5 text-sm text-ink bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${hasError ? "border-red-500" : "border-cream-300"}`;

  if (step === "requested") {
    const filename = target?.photo?.original_name || "photo";
    const sizeLabel = SIZE_OPTIONS.find((option) => option.value === resolution)?.label;
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
          <svg className="h-6 w-6 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 3v12m0 0 4-4m-4 4-4-4m-5 6v2a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2" /></svg>
        </div>
        <div>
          <h4 className="font-serif text-xl text-ink">Your download was requested</h4>
          <p className="mt-2 text-sm leading-relaxed text-muted">Your browser is downloading the selected photo.</p>
        </div>
        <p className="rounded-lg bg-cream-100 px-3 py-2 text-xs text-muted" title={filename}>{filename} · {sizeLabel}</p>
        <div className="flex justify-center gap-3">
          <button type="button" onClick={() => setStep("choose")} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Download again</button>
          <button type="button" onClick={onCancel} className="rounded-lg bg-ink px-4 py-2 text-sm text-white hover:bg-ink/85">Done</button>
        </div>
      </div>
    );
  }

  if (step === "preparing") {
    return (
      <div className="space-y-5 text-center" role="status" aria-live="polite">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
          <svg className="h-6 w-6 animate-spin text-ink" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        </div>
        <div>
          <h4 className="font-serif text-xl text-ink">We are preparing your photos</h4>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {notifyEmail
              ? "You will be notified by email when they are ready. You can stay on this page."
              : "This can take a few minutes. You can stay on this page — your download will appear here when it is ready."}
          </p>
        </div>
        {onCancel && (
          <div className="flex justify-center">
            <button type="button" onClick={onCancel} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Close</button>
          </div>
        )}
      </div>
    );
  }

  if (step === "ready") {
    return (
      <div className="space-y-5 text-left" aria-live="polite">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
            <svg className="h-6 w-6 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
          </div>
          <h4 className="font-serif text-xl text-ink">Your photos are ready to download</h4>
        </div>
        <ul className="space-y-2">
          {files.map((file, index) => (
            <li key={file.name} className="flex items-center justify-between gap-3 rounded-lg border border-cream-200 px-3 py-2.5">
              <span className="min-w-0">
                <span className="block truncate text-sm text-ink" title={file.name}>{file.name}</span>
                <span className="block text-xs text-muted">{formatMegabytes(file.size_bytes)}{startedFile === index ? " · downloading in your browser" : ""}</span>
              </span>
              <button
                type="button"
                onClick={() => handleDownloadFile(file, index)}
                disabled={startingFile !== null}
                className="shrink-0 rounded-lg bg-ink px-4 py-2 text-xs font-medium text-white hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label={`Download ${file.name}`}
              >
                {startingFile === index ? "Starting…" : "Download"}
              </button>
            </li>
          ))}
        </ul>
        {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
        {onCancel && (
          <div className="flex justify-end">
            <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">Done</button>
          </div>
        )}
      </div>
    );
  }

  if (step === "failed") {
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div>
          <h4 className="font-serif text-xl text-ink">We couldn't prepare your photos</h4>
          <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{failure}</p>
        </div>
        <div className="flex justify-center gap-3">
          <button type="button" onClick={() => { setErrors({}); setStep("choose"); }} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Back</button>
          <button type="button" onClick={() => prepareGallery(getDownloadAccess(sessionKey))} className="rounded-lg bg-ink px-4 py-2 text-sm text-white hover:bg-ink/85">Try again</button>
        </div>
      </div>
    );
  }

  if (step === "identity") {
    return (
      <form onSubmit={handleIdentity} noValidate className="space-y-5 text-left">
        <div>
          <h4 className="font-serif text-xl text-ink">Download Photos</h4>
          {requiresEmail && <p className="mt-1 text-sm leading-relaxed text-muted">Your email will be used to notify you when the files are ready.</p>}
        </div>
        {requiresEmail && <div className="space-y-1.5"><label htmlFor={`${uid}-email`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Email address</label><input id={`${uid}-email`} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@email.com" aria-invalid={Boolean(errors.email)} className={inputClass(errors.email)} />{errors.email && <p role="alert" className="text-xs text-red-600">{errors.email}</p>}</div>}
        {hasDownloadPin && <div className="space-y-1.5"><label htmlFor={`${uid}-pin`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Download PIN</label><input id={`${uid}-pin`} type="password" inputMode="numeric" autoComplete="off" maxLength={8} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))} placeholder="PIN from your photographer" aria-invalid={Boolean(errors.pin)} className={inputClass(errors.pin)} />{errors.pin && <p role="alert" className="text-xs text-red-600">{errors.pin}</p>}</div>}
        {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
        <div className="flex justify-end gap-2 pt-1">{!resumeJobId && <button type="button" onClick={() => setStep("choose")} className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">Back</button>}<button type="submit" disabled={submitting} className="rounded-lg bg-ink px-6 py-2.5 text-sm font-medium text-white hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-60">{submitting ? "Checking…" : "Next"}</button></div>
      </form>
    );
  }

  return (
    <form onSubmit={handleChoose} noValidate className="space-y-5 text-left">
      {!isPhoto && <fieldset className="space-y-2"><legend className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted">Choose photos</legend>{[{ id: "", name: "All photos", photo_count: photoCount }, ...photoSets].map((option) => <label key={option.id || "all"} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-cream-200 px-3 py-2.5 text-sm text-ink hover:bg-cream-100"><span className="flex items-center gap-2.5"><input type="radio" name={`${uid}-scope`} checked={scopeSetId === option.id} onChange={() => setScopeSetId(option.id)} className="accent-brand-green-600" />{option.name}</span><span className="text-xs text-muted">{option.photo_count ?? 0}</span></label>)}</fieldset>}
      {isPhoto && <p className="truncate text-sm text-muted">{target.photo?.original_name || "This photo"}</p>}
      <fieldset><legend className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted">Choose download size</legend><div className="grid grid-cols-2 gap-2">{allowedSizes.map((option) => { const selected = resolution === option.value; return <label key={option.value} className={`cursor-pointer rounded-lg border px-3 py-2.5 transition-colors ${selected ? "border-ink bg-white" : "border-cream-300 bg-cream-100 hover:bg-white"}`}><input type="radio" name={`${uid}-resolution`} value={option.value} checked={selected} onChange={() => setResolution(option.value)} className="sr-only" /><span className="block text-xs font-medium text-ink">{option.label}</span><span className="mt-0.5 block text-[11px] text-muted">{option.hint}</span></label>; })}</div></fieldset>
      <div className="rounded-lg bg-cream-100 px-3 py-2.5 text-sm text-ink"><span className="text-muted">Download to:</span> My Device</div>
      {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
      <div className="flex justify-end gap-2 pt-1">{onCancel && <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">Cancel</button>}<button type="submit" className="rounded-lg bg-ink px-6 py-2.5 text-sm font-medium text-white hover:bg-ink/85">Start Download</button></div>
    </form>
  );
}
