// File Location: frontend/src/pages/client/DownloadPage.jsx

import { useCallback, useEffect, useState } from "react";
import { useParams, Link, useLocation, useSearchParams } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
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
  const linkExpired = searchParams.get("link") === "expired";
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

  const title = gallery?.title || slug;
  const photographerName = gallery?.photographer_name || username;

  return (
    <div className="min-h-screen bg-[#FDFBF7]">
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-6 pb-8 pt-8 sm:px-8">
        {/* Pixieset-style header: the collection's name, then who shot it */}
        <header className="mb-10 sm:mb-14">
          <h1 className="font-serif text-2xl uppercase tracking-[0.14em] text-ink sm:text-3xl">{title}</h1>
          <p className="mt-1 text-[11px] uppercase tracking-[0.24em] text-muted">{photographerName}</p>
        </header>

        <main className="mx-auto w-full max-w-md flex-1 animate-fade-up text-center">
          {view.status === "loading" && (
            <div className="flex justify-center py-16" role="status" aria-label="Loading download options">
              <Spinner className="h-6 w-6 text-ink" />
            </div>
          )}

          {message && (
            <div className="space-y-4 py-10">
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
              linkExpired={linkExpired}
            />
          )}

          <Link
            to={`/g/${username}/${slug}`}
            className="mt-10 block text-sm underline underline-offset-2"
            style={{ color: "var(--ink)" }}
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
