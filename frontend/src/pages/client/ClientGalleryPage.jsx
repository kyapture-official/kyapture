// File Location: frontend/src/pages/client/ClientGalleryPage.jsx

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useClientStore } from "../../store/clientStore";
import { clientsApi } from "../../api/clientsApi";
import PublicMasonryGrid from "../../components/shared/PublicMasonryGrid";
import PhotoLightbox from "../../components/shared/PhotoLightbox";
import PasswordModal from "../../components/shared/PasswordModal";
import Spinner from "../../components/ui/Spinner";
import { formatDate } from "../../utils/formatters";

/**
 * Safely parses, normalizes, and appends alpha-channel hex codes to custom branding colors.
 * Prevents CSS syntax evaluation crashes on shorthand hex or legacy inputs.
 */
function getAlphaBrandingColor(hexColor, alphaHex = "14") {
  if (!hexColor || typeof hexColor !== "string") return undefined;
  const cleanHex = hexColor.trim();

  // 8-digit hex already carries its own alpha channel — leave it alone
  if (/^#[0-9A-F]{8}$/i.test(cleanHex)) {
    return cleanHex;
  }
  // Standard 6-digit hex format
  if (/^#[0-9A-F]{6}$/i.test(cleanHex)) {
    return `${cleanHex}${alphaHex}`;
  }
  // 4-digit shorthand (#RGBA) — expand to 8-digit, keeping its own alpha
  if (/^#[0-9A-F]{4}$/i.test(cleanHex)) {
    const [, r, g, b, a] = cleanHex;
    return `#${r}${r}${g}${g}${b}${b}${a}${a}`;
  }
  // Expand shorthand 3-digit hex format to 6-digit before appending alpha bytes
  if (/^#[0-9A-F]{3}$/i.test(cleanHex)) {
    const [, r, g, b] = cleanHex;
    return `#${r}${r}${g}${g}${b}${b}${alphaHex}`;
  }
  return cleanHex; // Fallback for RGB/RGBA or valid named variables
}

export default function ClientGalleryPage() {
  const { username, slug } = useParams();
  const navigate = useNavigate();

  // Key scoped to username:slug ensures tenant isolation in shared client environments
  const sessionKey = `${username}:${slug}`;
  const { sessions, setSession, hasHydrated } = useClientStore();
  const token = sessions[sessionKey] ?? null;

  // Selective Download tracking
  const [selectedAssetIds, setSelectedAssetIds] = useState(new Set());

  // Navigates to the Download Page with selected asset IDs passed in router state
  const handleDownloadSelected = () => {
    navigate(`/g/${username}/${slug}/download`, {
      state: { selectedIds: Array.from(selectedAssetIds) },
    });
  };

// Gallery structural metadata
  const [galleryTitle, setGalleryTitle] = useState("");
  const [photographerName, setPhotographerName] = useState("");
  const [photographerLogo, setPhotographerLogo] = useState(null);
  const [brandingColor, setBrandingColor] = useState(null);
  const [eventDate, setEventDate] = useState(null);
  const [photos, setPhotos] = useState([]);

  // UI state-machine properties
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(false);
  const [locked, setLocked] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState(null);

  // Lightbox tracking (null represents closed state)
  const [lightboxIndex, setLightboxIndex] = useState(null);

  

  const toggleSelection = useCallback((id) => {
    setSelectedAssetIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // System ref tracking to block async state-commit race conditions for gallery fetches
  const activeFetchId = useRef(0);

  // Separate generation counter for unlock attempts. Kept independent of
  // abortControllerRef's signal — fetchGallery aborts that same shared
  // controller as routine bookkeeping after a successful unlock, so the
  // signal's aborted state doesn't reliably mean "this unlock was superseded."
  const activeUnlockId = useRef(0);

  // Persistent AbortController reference shared by every network call this page
  // makes (initial fetch, retry, unlock) — there's only ever one request that
  // matters at a time, so a single shared handle is the correct single-flight guard.
  const abortControllerRef = useRef(null);

  /**
   * Applies and cleanses the dynamic branding color properties safely.
   */
  const applyGalleryData = useCallback((data) => {
    setGalleryTitle(data.title || "");
    setPhotographerName(data.photographer_name || "");
    setPhotographerLogo(data.photographer_logo || null);
    setEventDate(data.event_date || null);
    setPhotos(data.photos || []);
    setLocked(false);
    if (data.branding_color) {
      setBrandingColor(data.branding_color);
      document.documentElement.style.setProperty(
        "--brand-color",
        data.branding_color,
      );
    }
  }, []);

  /**
   * Orchestrates the primary read path for public tenant gallery data.
   */
  const fetchGallery = useCallback(
    async (currentToken, fetchId) => {
      // Abort any in-flight request managed by this component before starting a new fetch
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      // Reset transient visual errors to prevent old tenant state bleeding
      setLoading(true);
      setNotFound(false);
      setError(false);
      setPwError(null);

      try {
        const data = await clientsApi.getGallery(username, slug, currentToken, {
          signal: controller.signal,
        });

        // Guard statement: Discard payload if a newer fetch sequence has been initialized
        if (fetchId !== activeFetchId.current) return;

        if (data.requires_password) {
          setGalleryTitle(data.title || "");
          setPhotographerName(data.photographer_name || "");
          if (data.branding_color) {
            setBrandingColor(data.branding_color);
            document.documentElement.style.setProperty(
              "--brand-color",
              data.branding_color,
            );
          }

          // Evict invalidated tokens to restore system equilibrium
          if (currentToken) {
            setSession(sessionKey, null);
          }
          setLocked(true);
          setPhotos([]);
          return;
        }

        applyGalleryData(data);
      } catch (err) {
        // Gracefully capture aborted controller events without throwing state anomalies
        if (err.name === "AbortError" || err.code === "ERR_CANCELED") return;
        if (fetchId !== activeFetchId.current) return;

        const status = err.response?.status;
        if (status === 404) {
          setNotFound(true);
          return;
        }

        if (status === 401) {
          setSession(sessionKey, null);
          setLocked(true);
          setPhotos([]);
          return;
        }

        // Fallback path for generic unhandled network/server errors (500, timeouts)
        setError(true);
      } finally {
        if (fetchId === activeFetchId.current) {
          setLoading(false);
        }
      }
    },
    [username, slug, sessionKey, applyGalleryData, setSession],
  );

  // Triggers on initial mount and on tenant navigation once hydration completes
  useEffect(() => {
    if (!hasHydrated) return;

    const currentFetchId = ++activeFetchId.current;
    fetchGallery(token, currentFetchId);

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      // Cleanup custom variables to prevent style bleed across tenant pages
      document.documentElement.style.removeProperty("--brand-color");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, slug, hasHydrated]);

  /**
   * Handles security bypass validation against the verification endpoint.
   * Shares the page's single AbortController so a duplicate submit or a
   * navigate-away-mid-request cancels the stale unlock attempt cleanly.
   * Uses its own generation counter (activeUnlockId) to decide whether to
   * commit state — the shared controller's signal isn't reliable for that,
   * since a successful unlock's own follow-up fetchGallery call aborts it
   * as routine bookkeeping, not as a sign this attempt was superseded.
   */
  const handleUnlock = async (password) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const unlockId = ++activeUnlockId.current;

    setPwLoading(true);
    setPwError(null);
    try {
      const data = await clientsApi.unlock(username, slug, password, {
        signal: controller.signal,
      });
      setSession(sessionKey, data.access_token);

      const currentFetchId = ++activeFetchId.current;
      await fetchGallery(data.access_token, currentFetchId);
    } catch (err) {
      if (err.name === "AbortError" || err.code === "ERR_CANCELED") return;
      if (unlockId !== activeUnlockId.current) return;
      const msg =
        err.response?.data?.password?.[0] ||
        err.response?.data?.detail ||
        "Incorrect password. Please try again.";
      setPwError(msg);
    } finally {
      if (unlockId === activeUnlockId.current) {
        setPwLoading(false);
      }
    }
  };

  const retry = () => {
    const currentFetchId = ++activeFetchId.current;
    fetchGallery(token, currentFetchId);
  };

  // ── Render Path: Loading State ─────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50">
        <Spinner className="w-8 h-8 text-ink" />
        <p className="mt-4 text-xs tracking-widest text-muted uppercase font-light">
          Loading collection…
        </p>
      </div>
    );
  }

  // ── Render Path: 404 Not Found State ───────────────────────────────────────
  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 px-6 text-center">
        <h1 className="font-serif text-2xl text-ink mb-2">Gallery not found</h1>
        <p className="text-sm text-muted max-w-xs">
          This gallery doesn't exist or is no longer available.
        </p>
      </div>
    );
  }

  // ── Render Path: Generic Error State ───────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 px-6 text-center">
        <h1 className="font-serif text-2xl text-ink mb-2">
          Something went wrong
        </h1>
        <p className="text-sm text-muted max-w-xs mb-6">
          We couldn't load this gallery. Please try again.
        </p>
        <button
          onClick={retry}
          className="text-xs uppercase tracking-widest text-ink border border-ink/30 px-4 py-2 rounded-full hover:bg-ink/5 transition"
        >
          Retry
        </button>
      </div>
    );
  }

  // ── Render Path: Password Verification Gate ────────────────────────────────
  if (locked) {
    const backgroundGradientColor = getAlphaBrandingColor(brandingColor, "14");
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center px-6"
        style={{
          background: backgroundGradientColor
            ? `linear-gradient(180deg, ${backgroundGradientColor} 0%, #fdfbf7 100%)`
            : undefined,
        }}
      >
        {galleryTitle && (
          <h1 className="font-serif text-3xl text-ink mb-1 text-center">
            {galleryTitle}
          </h1>
        )}
        {photographerName && (
          <p className="text-xs uppercase tracking-[0.2em] text-muted mb-8">
            By {photographerName}
          </p>
        )}

        <PasswordModal
          open={locked}
          onSubmit={handleUnlock}
          error={pwError}
          loading={pwLoading}
        />
      </div>
    );
  }

  // ── Render Path: Unlocked Gallery View ─────────────────────────────────────
  const coverSrc = photos.length > 0
  ? (
      photos.find(p => p.is_cover)?.url ||
      photos[0]?.url ||
      photos[0]?.original_url ||
      photos[0]?.display_url ||
      photos[0]?.cover_url ||
      photos[0]?.thumbnail_url
    )
  : null;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── FULL-BLEED HERO COVER BANNER ──────────────────────────────── */}
      <section className="relative h-screen min-h-screen w-full overflow-hidden flex-shrink-0">
        {/* Background Image */}
        <div className="absolute inset-0">
          {coverSrc ? (
            <img
              src={coverSrc}
              alt=""
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full"
              style={{ backgroundColor: brandingColor || "#0f172a" }}
            />
          )}
          {/* Gradient overlay for text readability */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
        </div>

        {/* Hero Content */}
        <div className="relative z-10 flex flex-col items-center justify-center h-full px-6 text-center">
          {photographerName && (
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.25em] text-white/50 font-light mb-5">
              {photographerName}
            </p>
          )}

          <h1 className="font-serif text-4xl sm:text-5xl md:text-6xl lg:text-7xl text-white font-medium tracking-tight mb-4">
            {galleryTitle}
          </h1>

          <div className="h-px w-12 my-5 bg-white/30" />

          {eventDate && (
            <p className="text-xs sm:text-sm text-white/45 font-light tracking-widest uppercase mb-8">
              {formatDate(eventDate)}
            </p>
          )}

          {photos.length > 0 && (
            <button
              onClick={() => {
                document.getElementById("gallery-grid")?.scrollIntoView({ behavior: "smooth" });
              }}
              className="group flex items-center gap-2.5 text-[11px] uppercase tracking-[0.25em] text-white/90 hover:text-white border border-white/25 hover:border-white/50 rounded-full px-8 py-3.5 transition-all duration-300 hover:bg-white/10 cursor-pointer"
            >
              View Gallery
              <svg className="w-3.5 h-3.5 group-hover:translate-y-0.5 transition-transform duration-300" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
          )}
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2">
          <div className="w-5 h-8 rounded-full border border-white/20 flex items-start justify-center p-1.5">
            <div className="w-1 h-1 rounded-full bg-white/50 animate-bounce" />
          </div>
        </div>
      </section>

      {/* ── PHOTO GRID SECTION ────────────────────────────────────────── */}
      <main
        id="gallery-grid"
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16"
        style={{ animation: "fadeUp 0.5s ease both" }}
      >
        {/* Grid header */}
        <div className="max-w-6xl mx-auto mb-10 text-center">
          <h2 className="font-serif text-3xl text-ink mb-2">{galleryTitle}</h2>
          <div className="h-px w-12 mx-auto bg-ink/15" />
        </div>

        {/* Gallery Actions */}
        {photos.length > 0 && (
          <div className="flex justify-center mb-8 gap-3">
            <button
              onClick={handleDownloadSelected}
              className="text-xs uppercase tracking-widest text-ink border border-ink/30 px-6 py-2 rounded-full hover:bg-ink/5 transition"
            >
              {selectedAssetIds.size > 0
                ? `Download Selected (${selectedAssetIds.size})`
                : "Download Full Gallery"}
            </button>
          </div>
        )}

        {/* Dynamic Visual Masonry vs Empty State Fallback */}
        {photos.length === 0 ? (
          <div className="text-center py-24 border border-dashed border-slate-200 rounded-xl bg-slate-50">
            <p className="text-sm text-muted font-light">
              No images in this collection yet.
            </p>
          </div>
        ) : (
          <PublicMasonryGrid
            photos={photos}
            token={token}
            onPhotoClick={setLightboxIndex}
            selectedAssetIds={selectedAssetIds}
            onToggleSelection={toggleSelection}
          />
        )}

        {lightboxIndex !== null && (
          <PhotoLightbox
            photos={photos}
            index={lightboxIndex}
            token={token}
            onClose={() => setLightboxIndex(null)}
            onChange={setLightboxIndex}
            videoAccessToken={token}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="text-center py-8 text-xs text-muted border-t border-slate-200 mt-12">
        Delivered via <span className="font-serif text-sm text-ink">Kyapture</span>
      </footer>
    </div>
  );
}
