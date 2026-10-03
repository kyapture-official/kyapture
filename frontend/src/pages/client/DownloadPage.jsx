// File Location: frontend/src/pages/client/DownloadPage.jsx

import { useCallback, useEffect, useState } from "react";
import { useParams, Link, useLocation, useSearchParams } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import ClientLayout from "../../components/layout/ClientLayout";
import DownloadForm from "../../components/client/DownloadForm";
import Spinner from "../../components/ui/Spinner";

/**
 * Standalone download page for /g/:username/:slug/download. It works on a
 * direct open, a refresh, or the link in the "your photos are ready" email
 * (`?job=<id>` resumes that prepared download), because it never relies on
 * router state: the gallery's download policy comes from the API —
 * `has_download_pin` decides whether the PIN field is shown and
 * `download_policy.require_email` whether an email is asked for.
 *
 * The in-gallery Download button opens DownloadModal; both render the same
 * DownloadForm, so there is one download flow.
 */
export default function DownloadPage() {
  const { username, slug } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const resumeJobId = searchParams.get("job");
  const requestedSetId = searchParams.get("set") || location.state?.setId || null;

  // Unique session key prevents cross-tenant token collisions on identical gallery slugs
  const sessionKey = `${username}:${slug}`;
  const galleryToken = useClientStore((state) => state.sessions[sessionKey]) ?? null;

  const [view, setView] = useState({ status: "loading", gallery: null });
  const [attempt, setAttempt] = useState(0);
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
  const photoSets = gallery?.photo_sets || [];
  const setId = photoSets.some((set) => set.id === requestedSetId) ? requestedSetId : null;

  const message = {
    notfound: "This gallery doesn't exist or is no longer available.",
    disabled: "The photographer hasn't enabled downloads for this gallery.",
    locked: "This gallery is password protected. Open the gallery and enter its password first, then come back to download.",
    error: "We couldn't load this gallery. Please try again.",
  }[view.status];

  return (
    <ClientLayout>
      <div className="mx-auto max-w-md animate-fade-up px-6 py-24 text-center">
        <div
          className="mx-auto mb-8 flex h-20 w-20 select-none items-center justify-center rounded-full"
          style={{ background: "var(--cream2)" }}
        >
          <svg
            className="h-9 w-9"
            style={{ color: "var(--sand)" }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
        </div>

        <div className="mb-8">
          <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
            {resumeJobId ? "Your Download" : "Download Gallery"}
          </h1>
          {view.status === "ready" && (
            <p className="mt-3 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
              {resumeJobId
                ? "Confirm your details to get your photos."
                : "Choose a size, then confirm your details to start the download."}
            </p>
          )}
        </div>

        {view.status === "loading" && (
          <div className="flex justify-center py-8" role="status" aria-label="Loading download options">
            <Spinner className="h-6 w-6 text-ink" />
          </div>
        )}

        {message && (
          <div className="space-y-4">
            <p role="alert" className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{message}</p>
            {view.status === "error" && (
              <button
                type="button"
                onClick={retry}
                className="rounded-full border border-ink/30 px-4 py-2 text-xs uppercase tracking-widest text-ink transition hover:bg-ink/5"
              >
                Try again
              </button>
            )}
          </div>
        )}

        {view.status === "ready" && (
          <DownloadForm
            username={username}
            slug={slug}
            galleryToken={galleryToken}
            hasDownloadPin={Boolean(gallery.has_download_pin)}
            downloadPolicy={gallery.download_policy}
            target={{ type: "gallery", setId }}
            photoSets={photoSets}
            photoCount={gallery.photos_count || 0}
            resumeJobId={resumeJobId}
          />
        )}

        <Link
          to={`/g/${username}/${slug}`}
          className="mt-8 block text-sm underline underline-offset-2"
          style={{ color: "var(--ink)" }}
        >
          ← Back to gallery
        </Link>
      </div>
    </ClientLayout>
  );
}
