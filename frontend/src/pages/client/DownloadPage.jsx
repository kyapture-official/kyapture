// File Location: frontend/src/pages/client/DownloadPage.jsx

import React, { useState, useEffect } from "react";
import { useParams, Link, useLocation } from "react-router-dom";
import { useClientStore } from "../../store/clientStore";
import ClientLayout from "../../components/layout/ClientLayout";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import api from "../../api/axiosInstance";

// ── STATUS MACHINE ────────────────────────────────────────────────────────────
//  idle      → form shown, waiting for email input
//  loading   → ZIP compile + binary stream in progress
//  success   → file saved to browser, show confirmation
//  forbidden → 401/403 from backend (downloads disabled or session expired)
//  error     → network failure or unexpected server error
// ─────────────────────────────────────────────────────────────────────────────

export default function DownloadPage() {
  const { username, slug } = useParams();
  const location = useLocation();
  const selectedAssetIds = location.state?.selectedIds || [];

  // Unique session key prevents cross-tenant token collisions on identical gallery slugs
  const sessionKey = `${username}:${slug}`;
  const { sessions } = useClientStore();
  const galleryToken = sessions[sessionKey] ?? null;

  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle");
  const [progressMsg, setProgressMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  // Prevent double-scroll on mobile while the stream is loading
  useEffect(() => {
    if (status === "loading") {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.removeProperty("overflow");
    }
    return () => document.body.style.removeProperty("overflow");
  }, [status]);

  const handleRequest = async (e) => {
    e.preventDefault();
    if (!email.trim() || status === "loading") return;

    setStatus("loading");
    setProgressMsg("Connecting to download server…");
    setErrorMsg("");

    try {
      setProgressMsg("Compiling photos and generating ZIP archive…");

      // Dispatches request directly to the binary download API endpoint.
      const response = await api.post(
        `/public/${encodeURIComponent(username)}/${encodeURIComponent(slug)}/download/`,
        {
          email: email.trim(),
          token: galleryToken || undefined,
          asset_ids: selectedAssetIds,
        },

        {
          responseType: "blob", // Forces Axios to process the incoming response as binary ZIP data
          timeout: 120000, // 2-minute timeout boundary for large zip compilations
          onDownloadProgress: (evt) => {
            if (evt.total) {
              const pct = Math.round((evt.loaded * 100) / evt.total);
              setProgressMsg(`Downloading ZIP package (${pct}%)…`);
            } else {
              setProgressMsg("Downloading ZIP package…");
            }
          },
        },
      );

      setProgressMsg("Saving file to your device…");

      // Convert the binary stream response directly to a temporary Object URL download link
      const blob = new Blob([response.data], { type: "application/zip" });
      const downloadURL = window.URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = downloadURL;
      link.setAttribute("download", `${slug}-photos.zip`);
      document.body.appendChild(link);
      link.click();

      // Meticulous layout and memory cleanup
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadURL);

      setStatus("success");
    } catch (err) {
      // Decode error payloads safely since responseType is 'blob'
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          setErrorMsg(
            parsed.error || parsed.detail || "Download request failed.",
          );
        } catch {
          setErrorMsg("Failed to compile your download package.");
        }
      } else {
        setErrorMsg(err.response?.data?.detail || "Something went wrong.");
      }

      const httpStatus = err.response?.status;
      if (httpStatus === 401 || httpStatus === 403) {
        setStatus("forbidden");
      } else {
        setStatus("error");
      }
    } finally {
      setProgressMsg("");
    }
  };

  return (
    <ClientLayout>
      <div className="max-w-md mx-auto py-24 px-6 text-center animate-fade-up">
        {/* Dynamic System Icon */}
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-8 select-none"
          style={{ background: "var(--cream2)" }}
        >
          <svg
            className="w-9 h-9"
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

        {/* ── IDLE: Email Lead Capture Form ──────────────────────────────── */}
        {status === "idle" && (
          <form
            onSubmit={handleRequest}
            className="space-y-6 text-left"
            noValidate
          >
            <div className="text-center mb-8">
              <h1
                className="font-serif text-4xl"
                style={{ color: "var(--ink)" }}
              >
                Download Gallery
              </h1>
              <p
                className="text-sm leading-relaxed mt-3"
                style={{ color: "var(--muted)" }}
              >
                Your photographer has enabled downloads for this collection.
                Enter your email to receive your photos.
              </p>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="download-email"
                className="block text-xs uppercase tracking-wider font-medium select-none"
                style={{ color: "var(--muted)" }}
              >
                Email Address
              </label>
              <input
                type="email"
                id="download-email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@email.com"
                className="block w-full rounded-lg px-4 py-3 text-sm focus:outline-none transition-all duration-200"
                style={{
                  border: "1.5px solid var(--warm)",
                  background: "var(--cream2)",
                  color: "var(--ink)",
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = "var(--ink)";
                  e.target.style.background = "#fff";
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = "var(--warm)";
                  e.target.style.background = "var(--cream2)";
                }}
              />
              <p
                className="text-xs leading-relaxed mt-1"
                style={{ color: "var(--muted)", fontSize: 10 }}
              >
                Your email is shared with the photographer to log this download.
              </p>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full justify-center"
              disabled={!email.trim()}
            >
              Download Now
            </Button>
          </form>
        )}

        {/* ── LOADING: Streaming Progress States ─────────────────────────── */}
        {status === "loading" && (
          <div className="space-y-4 py-6" aria-live="polite">
            <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
              Preparing package…
            </h1>
            <p
              className="text-sm leading-relaxed max-w-xs mx-auto"
              style={{ color: "var(--muted)" }}
            >
              We are compiling and packaging your photos. This may take a moment
              for larger galleries — please keep this tab open.
            </p>
            <div className="flex flex-col items-center gap-4 pt-4">
              <Spinner />
              {progressMsg && (
                <span
                  className="text-xs tracking-wide"
                  style={{ color: "var(--muted)" }}
                >
                  {progressMsg}
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── SUCCESS: File Saved ────────────────────────────────────────── */}
        {status === "success" && (
          <div className="space-y-6">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center mx-auto"
              style={{ background: "rgba(74,124,111,0.10)" }}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--green)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>

            <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
              Ready!
            </h1>
            <p
              className="text-sm leading-relaxed max-w-sm mx-auto"
              style={{ color: "var(--muted)" }}
            >
              Your photos have been zipped and saved to your device. Check your
              browser's download folder.
            </p>

            <Link
              to={`/g/${username}/${slug}`}
              className="inline-flex items-center justify-center w-full px-8 py-3.5 rounded-xl text-sm font-medium transition-colors"
              style={{
                background: "var(--ink)",
                color: "var(--cream)",
                textDecoration: "none",
              }}
            >
              Return to Gallery
            </Link>
          </div>
        )}

        {/* ── FORBIDDEN: 401/403 ────────────────────────────────────────── */}
        {status === "forbidden" && (
          <div className="space-y-6">
            <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
              Not Available
            </h1>
            <p
              className="text-sm leading-relaxed max-w-sm mx-auto"
              style={{ color: "var(--muted)" }}
            >
              {errorMsg ||
                "Downloads are not enabled for this gallery, or your session has expired."}
            </p>
            <Link
              to={`/g/${username}/${slug}`}
              className="block text-sm underline underline-offset-2"
              style={{ color: "var(--ink)" }}
            >
              ← Back to gallery
            </Link>
          </div>
        )}

        {/* ── ERROR: 5xx / Network Failures ─────────────────────────────── */}
        {status === "error" && (
          <div className="space-y-6">
            <h1 className="font-serif text-4xl" style={{ color: "var(--ink)" }}>
              Something went wrong
            </h1>
            <p
              className="text-sm leading-relaxed max-w-sm mx-auto"
              style={{ color: "var(--muted)" }}
            >
              {errorMsg ||
                "We couldn't process your download request. Please try again or contact your photographer."}
            </p>
            <div className="flex gap-3 justify-center">
              <Button onClick={() => setStatus("idle")} variant="secondary">
                Try again
              </Button>
              <Link
                to={`/g/${username}/${slug}`}
                className="inline-flex items-center px-5 py-2.5 text-sm rounded-lg transition-colors"
                style={{
                  color: "var(--ink)",
                  border: "1px solid var(--warm)",
                  textDecoration: "none",
                }}
              >
                Back to gallery
              </Link>
            </div>
          </div>
        )}
      </div>
    </ClientLayout>
  );
}
