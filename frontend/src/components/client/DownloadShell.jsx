import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import PasswordModal from "../shared/PasswordModal";
import Spinner from "../ui/Spinner";

/**
 * The gallery behind a download page, loaded from the API: the page never relies
 * on router state, so a direct open, a refresh and an emailed link all work.
 * status: loading | ready | notfound | disabled | locked | error
 */
export function useDownloadGallery(username, slug) {
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
  return {
    view,
    retry,
    galleryToken,
    sessionKey,
    gallery,
    title: gallery?.title || slug,
    studio: gallery?.photographer_name || username,
  };
}

/**
 * The gallery password gate for a download page opened without an unlock session
 * (a fresh tab/browser): same unlock call and session as the gallery itself. On
 * success the session is stored, useDownloadGallery reloads with it and the page
 * carries on where it was -- never a dead end.
 */
function DownloadUnlockGate({ username, slug, sessionKey }) {
  const setSession = useClientStore((state) => state.setSession);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleUnlock = async (password) => {
    setLoading(true);
    setError(null);
    try {
      const data = await clientsApi.unlock(username, slug, password);
      setSession(sessionKey, data.access_token);
    } catch (err) {
      setError(err?.message || "Incorrect password. Please try again.");
      setLoading(false);
    }
  };

  return <PasswordModal open onSubmit={handleUnlock} error={error} loading={loading} />;
}

export const LOCKED_MESSAGE =
  "This gallery is password protected. Open the gallery and enter its password first, then come back to download.";

const GALLERY_MESSAGES = {
  notfound: "This gallery doesn't exist or is no longer available.",
  disabled: "The photographer hasn't enabled downloads for this gallery.",
  locked: LOCKED_MESSAGE,
  error: "We couldn't load this gallery. Please try again.",
};

export const pageButtonClass =
  "inline-flex w-full items-center justify-center bg-ink px-10 py-3.5 text-xs font-medium uppercase tracking-[0.25em] text-white transition hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:min-w-[11rem]";

/**
 * Every download page: gallery title (caps, bold) + studio name top-left, one
 * centered column, "Powered by KYAPTURE" at the bottom. No modal chrome.
 * `gallery` is the object from useDownloadGallery(); while the gallery itself
 * is not usable (missing / locked / downloads off) its message replaces the page.
 */
export default function DownloadShell({ username, slug, gallery, children, showBack = true, allowLocked = false }) {
  const { view, retry, title, studio, sessionKey } = gallery;
  // A locked gallery shows the password gate -- unless the page holds its own signed
  // grant (the emailed job link), which needs no gallery password.
  const locked = view.status === "locked";
  const showGate = locked && !allowLocked;
  const message = locked ? null : GALLERY_MESSAGES[view.status];

  return (
    <div className="min-h-screen bg-[#FDFBF7]">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-5 pb-8 pt-7 sm:px-8">
        {/* Pixieset-style header: the collection's name, then who shot it */}
        <header>
          <h1 className="font-serif text-xl font-bold uppercase tracking-[0.14em] text-ink sm:text-2xl">{title}</h1>
          <p className="mt-1 text-[11px] uppercase tracking-[0.24em] text-muted">{studio}</p>
        </header>

        <main className="mx-auto w-full max-w-[30rem] flex-1 animate-fade-up pt-10 sm:pt-16">
          {view.status === "loading" && (
            <div className="flex justify-center py-16" role="status" aria-label="Loading">
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

          {showGate && <DownloadUnlockGate username={username} slug={slug} sessionKey={sessionKey} />}

          {(view.status === "ready" || (locked && allowLocked)) && children}

          {showBack && (
            <Link
              to={`/g/${username}/${slug}`}
              className="mt-12 block text-center text-sm text-muted underline underline-offset-2 hover:text-ink"
            >
              ← Back to gallery
            </Link>
          )}
        </main>

        <footer className="pt-10 text-center text-[10px] uppercase tracking-[0.2em] text-muted">
          Powered by <span className="font-semibold text-ink">KYAPTURE</span>
        </footer>
      </div>
    </div>
  );
}
