// File Location: frontend/src/pages/client/DownloadFilePage.jsx

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import DownloadExpired from "../../components/client/DownloadExpired";
import DownloadShell, { LOCKED_MESSAGE, pageButtonClass, useDownloadGallery } from "../../components/client/DownloadShell";
import Spinner from "../../components/ui/Spinner";
import { formatBytes, jobViewFor, pollDelay } from "../../utils/downloadFlow.js";

const heading = "font-serif text-xl font-bold uppercase tracking-[0.16em] text-ink";

function startBrowserDownload(href) {
  // No `download` attribute: the server's attachment header names the file.
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * /g/:username/:slug/download/file/:jobId?key=...  — the prepared download's own page.
 *
 *   Page 3  "We are preparing your photos": spinner; the job is polled
 *           (2s, 5s, then every 10s). Leaving the page never cancels it — the
 *           visitor is emailed when it is ready, and this same URL shows Page 4.
 *   Page 4  "Your photos are ready to download": one row per ZIP part
 *           (name + size); a click starts that part's download.
 *   expired after the link's 7 days (or once the files were purged).
 *
 * The key in the URL is bound to this one job, so nothing is asked again — no
 * email, no PIN. Everything else (gallery password, limits) is still checked by
 * the server on every request.
 */
export default function DownloadFilePage() {
  const { username, slug, jobId } = useParams();
  const [searchParams] = useSearchParams();
  const linkToken = searchParams.get("key") || "";
  const gallery = useDownloadGallery(username, slug);
  const { view, galleryToken, title } = gallery;

  const [job, setJob] = useState({ view: "preparing", files: [], willEmail: false, error: "" });
  const [startingFile, setStartingFile] = useState(null);
  const [startedFile, setStartedFile] = useState(null);
  const [fileError, setFileError] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    document.title = `${title} - Download`;
  }, [title]);

  const fetchStatus = useCallback(
    () => clientsApi.getDownloadJob(username, slug, jobId, { linkToken, token: galleryToken }),
    [username, slug, jobId, linkToken, galleryToken],
  );

  // Poll until the job is ready (or gone). A network hiccup just waits for the next round.
  useEffect(() => {
    if (view.status !== "ready") return undefined;
    let cancelled = false;
    let attempt = 0;
    const check = async () => {
      let next = "retry";
      let data = null;
      try {
        data = await fetchStatus();
        next = jobViewFor({ data });
      } catch (error) {
        next = jobViewFor({ error });
      }
      if (cancelled) return;
      if (next === "retry" || next === "preparing") {
        if (next === "preparing" && data) setJob((current) => ({ ...current, view: "preparing", willEmail: Boolean(data.will_email) }));
        timer.current = window.setTimeout(check, pollDelay(attempt));
        attempt += 1;
        return;
      }
      setJob({
        view: next,
        files: data?.files || [],
        willEmail: Boolean(data?.will_email),
        error: data?.error || "",
      });
    };
    check();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [view.status, fetchStatus]);

  // The signed file link is minted fresh at the moment of the click, so an old tab
  // never holds a dead URL; if the download expired meanwhile the page says so.
  const handleDownloadFile = async (file, index) => {
    if (startingFile !== null) return;
    setStartingFile(index);
    setFileError("");
    try {
      const data = await fetchStatus();
      const next = jobViewFor({ data });
      if (next !== "ready") {
        setJob({ view: next, files: [], willEmail: false, error: data?.error || "" });
        return;
      }
      const fresh = data.files?.[index] || data.files?.find((entry) => entry.name === file.name);
      const href = clientsApi.buildJobFileHref(fresh?.url, { token: galleryToken });
      if (!href) {
        setJob({ view: "expired", files: [], willEmail: false, error: "" });
        return;
      }
      startBrowserDownload(href);
      setStartedFile(index);
    } catch (error) {
      const next = jobViewFor({ error });
      if (next === "expired" || next === "locked") setJob({ view: next, files: [], willEmail: false, error: "" });
      else setFileError(error?.message || "We couldn't start the download. Please try again.");
    } finally {
      setStartingFile(null);
    }
  };

  return (
    <DownloadShell username={username} slug={slug} gallery={gallery} showBack={job.view !== "expired"}>
      {job.view === "preparing" && (
        <div className="space-y-5 pt-16 text-center sm:pt-24" role="status" aria-live="polite">
          <div className="flex justify-center">
            <Spinner className="h-9 w-9 text-ink/70" />
          </div>
          <h2 className={heading + " pt-8"}>We are preparing your photos</h2>
          <div className="space-y-1 text-[15px] leading-7 text-muted">
            {job.willEmail && <p>You will be notified by email once your download is ready.</p>}
            <p>You can also stay on this page if you prefer.</p>
          </div>
        </div>
      )}

      {job.view === "ready" && (
        <div className="space-y-8 pt-6 text-center sm:pt-12" aria-live="polite">
          <div className="space-y-6">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border-2 border-brand-green-500 text-brand-green-600">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
            </div>
            <h2 className={heading}>Your photos are ready to download</h2>
            <p className="text-[15px] text-muted">Click the link(s) below to start the download.</p>
          </div>
          <ul className="space-y-3 text-left">
            {job.files.map((file, index) => (
              <li key={file.name}>
                <button
                  type="button"
                  onClick={() => handleDownloadFile(file, index)}
                  disabled={startingFile !== null}
                  className="flex w-full items-center justify-between gap-4 border border-cream-300 bg-cream-100 px-5 py-5 text-left text-sm text-ink transition hover:bg-cream-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-wait"
                  aria-label={`Download ${file.name}`}
                >
                  <span className="min-w-0 flex-1 break-all">{file.name}</span>
                  <span className="shrink-0 text-xs text-muted">
                    {startingFile === index ? "Starting…" : startedFile === index ? "Downloading…" : formatBytes(file.size_bytes)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {fileError && <p role="alert" className="bg-red-50 px-3 py-2 text-sm text-red-700">{fileError}</p>}
        </div>
      )}

      {job.view === "expired" && <DownloadExpired username={username} slug={slug} />}

      {job.view === "locked" && (
        <p role="alert" className="py-10 text-center text-sm leading-relaxed text-muted">{LOCKED_MESSAGE}</p>
      )}

      {job.view === "failed" && (
        <div className="space-y-8 text-center" role="alert">
          <h2 className={heading}>We couldn&apos;t prepare your photos</h2>
          <p className="text-[15px] leading-8 text-muted">{job.error || "Please request a new download."}</p>
          <div className="flex justify-center">
            <Link to={`/g/${username}/${slug}/download`} className={pageButtonClass}>Request a new download</Link>
          </div>
        </div>
      )}
    </DownloadShell>
  );
}
