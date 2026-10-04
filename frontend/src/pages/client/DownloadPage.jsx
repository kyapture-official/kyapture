// File Location: frontend/src/pages/client/DownloadPage.jsx

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import DownloadAuthStep from "../../components/client/DownloadAuthStep";
import DownloadChooseStep from "../../components/client/DownloadChooseStep";
import DownloadJobProgress from "../../components/client/DownloadJobProgress";
import Spinner from "../../components/ui/Spinner";
import { defaultSize, gateNeeds, initialStep, sizeOptions } from "../../utils/downloadFlow.js";

/**
 * Full-page gallery download for /g/:username/:slug/download — opened in a new
 * tab by the gallery header's Download icon, or from the "your photos are ready"
 * email (`?job=<id>` resumes that prepared download). It never relies on router
 * state: the gallery's effective download policy comes from the API.
 *
 *   auth    Page 1  "Download Photos": email and/or Download PIN, only when still owed
 *   choose  Page 2  Choose Photos / Download Size / Download To
 *   job     after START DOWNLOAD: the ZIP is prepared, then offered (see DownloadJobProgress)
 *
 * Page 1 is skipped when nothing is owed (no email required, no PIN) or the
 * session already earned access. Skipping it is only a convenience: the server
 * checks email and PIN again on every request.
 */
export default function DownloadPage() {
  const { username, slug } = useParams();
  const [searchParams] = useSearchParams();
  const resumeJobId = searchParams.get("job");
  const linkExpired = searchParams.get("link") === "expired";

  // Unique session key prevents cross-tenant token collisions on identical gallery slugs
  const sessionKey = `${username}:${slug}`;
  const galleryToken = useClientStore((state) => state.sessions[sessionKey]) ?? null;
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);

  const [view, setView] = useState({ status: "loading", gallery: null });
  const [attempt, setAttempt] = useState(0);
  const [step, setStep] = useState(null);
  const [access, setAccess] = useState(null);
  const [request, setRequest] = useState(null);
  const [notice, setNotice] = useState(linkExpired ? "That download link has expired. Prepare your download again below." : "");
  const retry = useCallback(() => {
    setView({ status: "loading", gallery: null });
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const data = await clientsApi.getGallery(username, slug, galleryToken, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (data.requires_password) setView({ status: "locked", gallery: data });
        else if (!data.allow_download) setView({ status: "disabled", gallery: data });
        else setView({ status: "ready", gallery: data });
      } catch (err) {
        if (err?.name === "AbortError" || err?.code === "ERR_CANCELED") return;
        if (err?.status === 404) setView({ status: "notfound", gallery: null });
        else if (err?.status === 401) setView({ status: "locked", gallery: null });
        else setView({ status: "error", gallery: null });
      }
    })();
    return () => controller.abort();
  }, [username, slug, galleryToken, attempt]);

  const gallery = view.gallery;
  const policy = gallery?.download_policy;
  const hasPin = Boolean(gallery?.has_download_pin);
  const studio = gallery?.photographer_name || username;
  const title = gallery?.title || slug;

  useEffect(() => {
    document.title = `${title} - Download`;
  }, [title]);

  // The first page is decided once, when the policy first arrives (a remembered
  // token from earlier in this session already counts as access).
  useEffect(() => {
    if (view.status !== "ready" || step !== null) return;
    const remembered = useClientStore.getState().getDownloadAccess(sessionKey);
    const needs = gateNeeds({ policy, hasPin, access: remembered });
    setAccess(remembered);
    setStep(initialStep({ needsGate: needs.needsGate, resumeJobId }));
  }, [view.status, step, policy, hasPin, sessionKey, resumeJobId]);

  // What "prepare again" means when a job was resumed from the email link.
  const resumedRequest = useMemo(
    () => ({ resolution: defaultSize(sizeOptions(policy)) }),
    [policy],
  );

  const needs = gateNeeds({ policy, hasPin, access });

  const goToPage2 = (grantedAccess) => {
    setAccess(grantedAccess);
    setNotice("");
    setStep(resumeJobId ? "job" : "choose");
  };

  const startDownload = (choice) => {
    setRequest(choice);
    setNotice("");
    setStep("job");
  };

  // The server said the session token is no good any more: ask again on Page 1.
  const sessionExpired = useCallback(() => {
    setDownloadAccess(sessionKey, null);
    setAccess(null);
    setNotice("Your download session expired. Please confirm your details again.");
    setStep("auth");
  }, [sessionKey, setDownloadAccess]);

  const message = {
    notfound: "This gallery doesn't exist or is no longer available.",
    disabled: "The photographer hasn't enabled downloads for this gallery.",
    locked: "This gallery is password protected. Open the gallery and enter its password first, then come back to download.",
    error: "We couldn't load this gallery. Please try again.",
  }[view.status];

  // Nothing to ask once the total download limit is hit — unless this visit is
  // only collecting a download that was already prepared.
  const limitBlocked = Boolean(policy?.limit_reached) && !resumeJobId && step !== "job";

  return (
    <div className="min-h-screen bg-[#FDFBF7]">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-5 pb-8 pt-7 sm:px-8">
        {/* Pixieset-style header: the collection's name, then who shot it */}
        <header>
          <h1 className="font-serif text-xl font-bold uppercase tracking-[0.14em] text-ink sm:text-2xl">{title}</h1>
          <p className="mt-1 text-[11px] uppercase tracking-[0.24em] text-muted">{studio}</p>
        </header>

        <main className="mx-auto w-full max-w-[30rem] flex-1 animate-fade-up pt-10 sm:pt-16">
          {(view.status === "loading" || (view.status === "ready" && step === null)) && (
            <div className="flex justify-center py-16" role="status" aria-label="Loading download options">
              <Spinner className="h-6 w-6 text-ink" />
            </div>
          )}

          {message && (
            <div className="space-y-4 py-10 text-center">
              <p role="alert" className="text-sm leading-relaxed text-muted">{message}</p>
              {view.status === "error" && (
                <button
                  type="button"
                  onClick={retry}
                  className="w-full border border-ink/30 px-4 py-3 text-xs uppercase tracking-widest text-ink transition hover:bg-ink/5 sm:w-auto"
                >
                  Try again
                </button>
              )}
            </div>
          )}

          {view.status === "ready" && limitBlocked && (
            <p role="alert" className="bg-red-50 px-3 py-3 text-center text-sm text-red-700">
              Download limit reached. Contact {studio}.
            </p>
          )}

          {view.status === "ready" && !limitBlocked && step === "auth" && (
            <DownloadAuthStep
              username={username}
              slug={slug}
              galleryToken={galleryToken}
              studio={studio}
              needsEmail={needs.needsEmail}
              needsPin={needs.needsPin}
              notice={notice}
              onGranted={goToPage2}
            />
          )}

          {view.status === "ready" && !limitBlocked && step === "choose" && (
            <DownloadChooseStep
              policy={policy}
              photoSets={gallery.photo_sets || []}
              photoCount={gallery.photos_count || 0}
              studio={studio}
              notice={notice}
              onStart={startDownload}
            />
          )}

          {view.status === "ready" && step === "job" && (
            <DownloadJobProgress
              username={username}
              slug={slug}
              galleryToken={galleryToken}
              studio={studio}
              access={access}
              request={request || resumedRequest}
              resumeJobId={request ? null : resumeJobId}
              onBack={() => setStep("choose")}
              onSessionExpired={sessionExpired}
            />
          )}

          <Link
            to={`/g/${username}/${slug}`}
            className="mt-12 block text-center text-sm text-muted underline underline-offset-2 hover:text-ink"
          >
            ← Back to gallery
          </Link>
        </main>

        <footer className="pt-10 text-center text-[10px] uppercase tracking-[0.2em] text-muted">
          Powered by <span className="font-semibold text-ink">KYAPTURE</span>
        </footer>
      </div>
    </div>
  );
}
