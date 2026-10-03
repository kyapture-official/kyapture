// File Location: frontend/src/pages/client/DownloadPage.jsx

import React from "react";
import { useParams, Link, useLocation } from "react-router-dom";
import { useClientStore } from "../../store/clientStore";
import ClientLayout from "../../components/layout/ClientLayout";
import DownloadForm from "../../components/client/DownloadForm";

/**
 * Standalone download page for /g/:username/:slug/download — kept so deep
 * links keep working. The in-gallery Download button uses DownloadModal;
 * both render the same DownloadForm, so there is one download flow:
 * authorize on the server (email, plus the PIN when the gallery needs one),
 * then stream the file/ZIP via a plain download URL.
 *
 * It does not need router state to know whether a PIN exists: if the
 * gallery has one and the form wasn't told, the server's pin_required
 * answer makes the form reveal the PIN field.
 */
export default function DownloadPage() {
  const { username, slug } = useParams();
  const location = useLocation();
  const setId = location.state?.setId || null;
  const hasDownloadPin = Boolean(location.state?.hasDownloadPin);

  // Unique session key prevents cross-tenant token collisions on identical gallery slugs
  const sessionKey = `${username}:${slug}`;
  const galleryToken = useClientStore((state) => state.sessions[sessionKey]) ?? null;

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

        <>
            <div className="mb-8">
              <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
                Download Gallery
              </h1>
              <p className="mt-3 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                Choose a size, then confirm your details to start the download.
              </p>
            </div>
            <DownloadForm
              username={username}
              slug={slug}
              galleryToken={galleryToken}
              hasDownloadPin={hasDownloadPin}
              downloadPolicy={location.state?.downloadPolicy}
              target={{ type: "gallery", setId }}
              photoSets={location.state?.photoSets || []}
              photoCount={location.state?.photoCount || 0}
            />
            <Link
              to={`/g/${username}/${slug}`}
              className="mt-8 block text-sm underline underline-offset-2"
              style={{ color: "var(--ink)" }}
            >
              ← Back to gallery
            </Link>
        </>
      </div>
    </ClientLayout>
  );
}
