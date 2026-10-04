import { useCallback, useEffect, useRef, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { blockedMessage, isBlockedCode } from "../../utils/downloadFlow.js";

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
const primaryButton =
  "w-full bg-ink px-8 py-3.5 text-xs font-medium uppercase tracking-[0.2em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto";
const secondaryButton =
  "w-full border border-ink/30 px-6 py-3.5 text-xs uppercase tracking-[0.2em] text-ink transition hover:bg-ink/5 sm:w-auto";

/**
 * Everything after START DOWNLOAD for a gallery / set: the ZIP is PREPARED in the
 * background (preparing -> ready with a Download button, or failed). The later
 * chunks restyle these screens; the behaviour here is the existing 1R.4 flow.
 *
 * `request` is the already-chosen { resolution, setId?, setIds? }; `access` the
 * download token earned on Page 1 (null when the gallery needs none). With
 * `resumeJobId` (the link in the "ready" email) it resumes that job instead of
 * preparing a new one. Leaving the page never cancels a prepared download.
 */
export default function DownloadJobProgress({
  username,
  slug,
  galleryToken = null,
  studio,
  access = null,
  request,
  resumeJobId = null,
  onBack,
  onSessionExpired,
}) {
  const [step, setStep] = useState("preparing");
  const [notifyEmail, setNotifyEmail] = useState(access?.email || null);
  const [files, setFiles] = useState([]);
  const [expiresAt, setExpiresAt] = useState(null);
  const [failure, setFailure] = useState({ message: "", code: "" });
  const [startingFile, setStartingFile] = useState(null);
  const [startedFile, setStartedFile] = useState(null);
  const [fileError, setFileError] = useState("");

  const activeJob = useRef(null); // { id, startedAt }
  const pollTimer = useRef(null);
  const pollAttempt = useRef(0);
  const unmounted = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) window.clearTimeout(pollTimer.current);
    pollTimer.current = null;
  }, []);

  const failWith = useCallback(
    (message, code = "") => {
      stopPolling();
      if (unmounted.current) return;
      setFailure({ message, code });
      setStep("failed");
    },
    [stopPolling],
  );

  const checkJob = useCallback(async () => {
    const job = activeJob.current;
    if (!job || unmounted.current) return;
    try {
      const status = await clientsApi.getDownloadJob(username, slug, job.id, {
        downloadToken: access?.token, token: galleryToken,
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
        stopPolling();
        onSessionExpired?.();
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
  }, [username, slug, galleryToken, access, stopPolling, failWith, onSessionExpired]);

  const beginPolling = useCallback(
    (jobId) => {
      stopPolling();
      activeJob.current = { id: jobId, startedAt: Date.now() };
      pollAttempt.current = 0;
      setStep("preparing");
      checkJob();
    },
    [checkJob, stopPolling],
  );

  const prepare = useCallback(async () => {
    setFailure({ message: "", code: "" });
    setStep("preparing");
    try {
      const job = await clientsApi.prepareGalleryDownload(username, slug, {
        downloadToken: access?.token, token: galleryToken, ...request,
      });
      if (unmounted.current) return;
      beginPolling(job.job_id);
    } catch (err) {
      if (unmounted.current) return;
      if (err?.code === "download_access_expired") {
        onSessionExpired?.();
      } else if (err?.status === 429) {
        failWith("Too many attempts. Please wait a minute and try again.");
      } else if (isBlockedCode(err?.code)) {
        failWith(blockedMessage(err.code, studio, err.message), err.code);
      } else {
        failWith(err?.message || "We couldn't start preparing your photos. Please try again.", err?.code || "");
      }
    }
  }, [username, slug, galleryToken, access, request, studio, beginPolling, failWith, onSessionExpired]);

  // Start once on arrival: resume the emailed job, or prepare the chosen download.
  // Re-running on prop changes would queue duplicates, so this is deliberately mount-only.
  useEffect(() => {
    unmounted.current = false;
    if (resumeJobId) beginPolling(resumeJobId);
    else prepare();
    return () => {
      unmounted.current = true;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A ready file's signed link lives for the job's lifetime, but we still ask the
  // server at the moment of the click: if the job expired or its file vanished the
  // visitor gets "prepare again" instead of a dead link.
  const handleDownloadFile = async (file, index) => {
    const job = activeJob.current;
    if (!job || startingFile !== null) return;
    setStartingFile(index);
    setFileError("");
    try {
      const status = await clientsApi.getDownloadJob(username, slug, job.id, {
        downloadToken: access?.token, token: galleryToken,
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
      if (err?.code === "download_access_expired") onSessionExpired?.();
      else setFileError(err?.message || "We couldn't start the download. Please try again.");
    } finally {
      if (!unmounted.current) setStartingFile(null);
    }
  };

  if (step === "preparing") {
    return (
      <div className="space-y-5 py-4 text-center" role="status" aria-live="polite">
        <div className="mx-auto flex h-14 w-14 items-center justify-center">
          <svg className="h-7 w-7 animate-spin text-ink" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        </div>
        <div>
          <h2 className={heading}>Preparing your download...</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {notifyEmail || access?.email
              ? "You will be notified by email once your download is ready. You can also stay on this page if you prefer."
              : "This can take a few minutes. You can stay on this page — your download will appear here when it is ready."}
          </p>
          <p className="mt-2 text-xs text-muted">Closing this page won&apos;t cancel it.</p>
        </div>
      </div>
    );
  }

  if (step === "ready") {
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border-2 border-brand-green-500 text-brand-green-600">
          <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
        </div>
        <h2 className={heading}>Your photos are ready to download</h2>
        <ul className="space-y-4">
          {files.map((file, index) => (
            <li key={file.name} className="space-y-3">
              <button
                type="button"
                onClick={() => handleDownloadFile(file, index)}
                disabled={startingFile !== null}
                className={primaryButton + " !py-4 !text-sm"}
                aria-label={`Download ${file.name}`}
              >
                {startingFile === index ? "Starting…" : "Download"}
              </button>
              <p className="bg-cream-100 px-3 py-2.5 text-sm text-ink">
                <span className="block truncate" title={file.name}>{file.name}</span>
                <span className="text-xs text-muted">{formatMegabytes(file.size_bytes)}{startedFile === index ? " · downloading in your browser" : ""}</span>
              </p>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted">{validityLabel(expiresAt)}</p>
        {fileError && <p role="alert" className="bg-red-50 px-3 py-2 text-xs text-red-700">{fileError}</p>}
      </div>
    );
  }

  // failed / expired / blocked
  const expired = failure.code === "download_expired" || failure.code === "file_missing";
  const blocked = isBlockedCode(failure.code);
  return (
    <div className="space-y-5 text-center" aria-live="polite">
      <div>
        <h2 className={heading}>
          {expired ? "This link has expired" : blocked ? "Download unavailable" : "We couldn't prepare your photos"}
        </h2>
        <p role="alert" className="mt-3 bg-red-50 px-3 py-2 text-sm text-red-700">
          {expired ? "Link expired — prepare your download again to get a fresh one." : failure.message}
        </p>
      </div>
      <div className="flex flex-col justify-center gap-3 sm:flex-row">
        <button type="button" onClick={onBack} className={secondaryButton}>Back</button>
        {!blocked && (
          <button type="button" onClick={prepare} className={primaryButton}>{expired ? "Prepare again" : "Try again"}</button>
        )}
      </div>
    </div>
  );
}
