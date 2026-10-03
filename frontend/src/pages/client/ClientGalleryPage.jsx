// File Location: frontend/src/pages/client/ClientGalleryPage.jsx

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useClientStore } from "../../store/clientStore";
import { clientsApi } from "../../api/clientsApi";
import PublicMasonryGrid from "../../components/shared/PublicMasonryGrid";
import PhotoLightbox from "../../components/shared/PhotoLightbox";
import PasswordModal from "../../components/shared/PasswordModal";
import GallerySkeleton from "../../components/client/GallerySkeleton";
import DownloadModal from "../../components/client/DownloadModal";
import FavoriteEmailModal from "../../components/client/FavoriteEmailModal";
import FavoritesPanel from "../../components/client/FavoritesPanel";
import { useVisitorStore } from "../../store/visitorStore";
import ShareMenu from "../../components/shared/ShareMenu";
import { resolveShareUrl } from "../../utils/share";
import Spinner from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import { formatDate } from "../../utils/formatters";
import { resolveDesignSettings } from "../../utils/designSettings";
import { Download, Heart, Play } from "lucide-react";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSetId = searchParams.get("set");

  // Key scoped to username:slug ensures tenant isolation in shared client environments
  const sessionKey = `${username}:${slug}`;
  const { sessions, setSession, hasHydrated, getOrCreateClientUid } = useClientStore();
  const token = sessions[sessionKey] ?? null;
  const toast = useToast();

  // Phase 3 — Photo Sets, Favorites, Slideshow, Download PIN
  const [photoSets, setPhotoSets] = useState([]);
  const [activeSetId, setActiveSetId] = useState(null);
  const [favoritedIds, setFavoritedIds] = useState(new Set());
  // Favorites carry the visitor's email: asked ONCE (first heart), remembered in
  // this browser, and also learned from the server when it already holds one.
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [emailPromptOpen, setEmailPromptOpen] = useState(false);
  const [serverEmail, setServerEmail] = useState(null);
  const pendingFavoriteRef = useRef(null);
  const visitorProfile = useVisitorStore((state) => state.profiles[sessionKey]);
  const setVisitorProfile = useVisitorStore((state) => state.setProfile);
  const [hasDownloadPin, setHasDownloadPin] = useState(false);
  const [downloadPolicy, setDownloadPolicy] = useState({
    allowed_sizes: ["download", "web"],
    require_email: true,
  });
  const [isPasswordProtected, setIsPasswordProtected] = useState(false);
  const [slideshowIndex, setSlideshowIndex] = useState(null);
  const [slideshowAutoplay, setSlideshowAutoplay] = useState(false);
  // The gallery's canonical share link as sent by the server (credential-free).
  const [shareUrl, setShareUrl] = useState(null);

  // The client's identity for favorites: the verified unlock token for a
  // protected gallery, or a per-browser generated id for an open one —
  // see Favorite's docstring (backend apps/clients/models.py) for why.
  // Built lazily inside event handlers/effects (never during render) since
  // resolving the "open gallery" branch can write a freshly-generated uid
  // into the client store.
  const getClientIdentity = useCallback(
    () => (isPasswordProtected ? { token } : { clientUid: getOrCreateClientUid(sessionKey) }),
    [isPasswordProtected, token, sessionKey, getOrCreateClientUid],
  );

  // Download is always an explicit action: it opens the download dialog
  // (size choice, plus email/PIN only when authorization is needed), and
  // only then asks the server to authorize. Browsing never reaches it.
  // target: { type: 'gallery', setId? } | { type: 'photo', photo } | null
  const [downloadTarget, setDownloadTarget] = useState(null);

  const openGalleryDownload = () =>
    setDownloadTarget({ type: "gallery", setId: activeSetId || null });

  const openPhotoDownload = (photo) => {
    if (!photo?.download_url) {
      toast("This file isn't available for download.", "error");
      return;
    }
    setDownloadTarget({ type: "photo", photo });
  };

  const openSlideshow = () => {
    if (photos.length === 0) return;
    setSlideshowAutoplay(true);
    setSlideshowIndex(0);
  };

// Gallery structural metadata
  const [galleryTitle, setGalleryTitle] = useState("");
  const [photographerName, setPhotographerName] = useState("");
  const [photographerLogo, setPhotographerLogo] = useState(null);
  // A logo URL that fails to load is hidden rather than shown as a broken image.
  const [logoFailed, setLogoFailed] = useState(false);
  const [brandingColor, setBrandingColor] = useState(null);
  const [eventDate, setEventDate] = useState(null);
  const [coverUrl, setCoverUrl] = useState(null);
  const [coverMediumUrl, setCoverMediumUrl] = useState(null);
  // Failures are shown as failures (with a retry), not as an empty set.
  const [setLoadError, setSetLoadError] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const [allowDownload, setAllowDownload] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [photosCount, setPhotosCount] = useState(0);

  // Phase 2 large-gallery pagination: the initial gallery payload embeds
  // only the FIRST page of READY photos (see PublicGallerySerializer /
  // GalleryMediaPagination). These track whether more pages exist and
  // drive the "Load more" control below the grid.
  const [photosHasMore, setPhotosHasMore] = useState(false);
  const [loadingMorePhotos, setLoadingMorePhotos] = useState(false);
  const [photosLoadingSet, setPhotosLoadingSet] = useState(false);
  const nextPageRef = useRef(2);
  const activeSetRequestId = useRef(0);

  // Phase 2, item E — the gallery's persisted design_settings (Phase 1
  // persisted them; this is what actually applies them client-side).
  // resolveDesignSettings() supplies sane defaults so a gallery with no
  // design_settings yet renders exactly as before (serif typography,
  // light theme, vertical masonry, regular thumbnails).
  const [designSettings, setDesignSettings] = useState(null);
  const resolvedDesign = resolveDesignSettings(designSettings);

  // UI state-machine properties
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(false);
  const [locked, setLocked] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState(null);

  // Lightbox tracking (null represents closed state)
  const [lightboxIndex, setLightboxIndex] = useState(null);

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
    setShareUrl(data.share_url || null);
    setLogoFailed(false);
    setEventDate(data.event_date || null);
    setCoverUrl(data.cover_url || null);
    setCoverMediumUrl(data.cover_medium_url || null);
    setAllowDownload(Boolean(data.allow_download));
    setPhotos(data.photos || []);
    setPhotosCount(Number(data.photos_count) || (data.photos || []).length);
    setPhotosHasMore(Boolean(data.photos_has_more));
    nextPageRef.current = 2;
    setDesignSettings(data.design_settings || null);
    setLocked(false);
    setPhotoSets(data.photo_sets || []);
    setHasDownloadPin(Boolean(data.has_download_pin));
    setDownloadPolicy(data.download_policy || {
      allowed_sizes: ["download", "web"],
      require_email: true,
    });
    setIsPasswordProtected(Boolean(data.is_password_protected));
    if (data.branding_color) {
      setBrandingColor(data.branding_color);
      document.documentElement.style.setProperty(
        "--brand-color",
        data.branding_color,
      );
    }
  }, []);

  /**
   * Batch-loads this client's favorited photo ids in ONE request — never
   * per-photo. Best-effort: a failure here just means hearts start
   * unfilled, not a page-level error state.
   */
  const loadFavorites = useCallback(
    async (currentToken, identity) => {
      try {
        const data = await clientsApi.getFavorites(username, slug, identity);
        setFavoritedIds(new Set(data.favorited_ids || []));
        if (data.email) {
          setServerEmail(data.email);
          const known = useVisitorStore.getState().getProfile(`${username}:${slug}`);
          if (!known?.email) useVisitorStore.getState().setProfile(`${username}:${slug}`, { email: data.email, name: known?.name || "" });
        }
      } catch {
        // Non-fatal — see comment above.
      }
    },
    [username, slug],
  );

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
          setIsPasswordProtected(true);
          setPhotos([]);
          return;
        }

        applyGalleryData(data);

        // Batch-fetch favorites AFTER we know whether this gallery is
        // password-protected (identity depends on it) — fire-and-forget,
        // never blocks the gallery from rendering.
        const identity = data.is_password_protected
          ? { token: currentToken }
          : { clientUid: getOrCreateClientUid(sessionKey) };
        loadFavorites(currentToken, identity);
      } catch (err) {
        // Gracefully capture aborted controller events without throwing state anomalies
        if (err.name === "AbortError" || err.code === "ERR_CANCELED") return;
        if (fetchId !== activeFetchId.current) return;

        // clientsApi.js's normalizeError() sets `.status` directly on the
        // thrown Error (not `.response.status` — these are already-normalized
        // errors, not raw axios errors), so that's what must be read here.
        const status = err.status;
        if (status === 404) {
          // Nonexistent gallery AND expired/unpublished/deactivated gallery
          // both resolve to this same 404 server-side (PublicGalleryView's
          // lookup query intentionally can't distinguish "never existed"
          // from "no longer available" without leaking which one it is to
          // an unauthenticated guest), so both show the same not-found state.
          setNotFound(true);
          return;
        }

        if (status === 401) {
          // Invalid/expired unlock token for a password-protected gallery —
          // drop the stale session token and show the password gate again.
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
    [username, slug, sessionKey, applyGalleryData, setSession, loadFavorites, getOrCreateClientUid],
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
      setPwError(err.message || "Incorrect password. Please try again.");
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

  /**
   * Fetches the next page of READY photos/videos and appends it to the
   * grid in place — the visitor never loses their scroll position or
   * selection state the way a full gallery re-fetch would.
   */
  const loadMorePhotos = async () => {
    if (loadingMorePhotos || !photosHasMore) return;
    setLoadingMorePhotos(true);
    setLoadMoreError(false);
    try {
      const data = await clientsApi.getGalleryPhotosBySet(
        username,
        slug,
        nextPageRef.current,
        activeSetId,
        token,
      );
      setPhotos((prev) => [...prev, ...(data.results || [])]);
      setPhotosHasMore(Boolean(data.next));
      nextPageRef.current += 1;
    } catch (err) {
      if (err.name === "AbortError" || err.code === "ERR_CANCELED") return;
      // A failed "load more" isn't fatal to the page already on screen —
      // leave photosHasMore as-is and offer an inline retry.
      setLoadMoreError(true);
    } finally {
      setLoadingMorePhotos(false);
    }
  };

  /**
   * Loads a server-filtered first page for a photo set. A monotonically
   * increasing request id prevents a slower prior tab from replacing the
   * currently selected set after a quick switch.
   */
  const loadPhotoSet = useCallback(
    async (setId) => {
      const requestId = ++activeSetRequestId.current;
      setPhotosLoadingSet(true);
      setSetLoadError(false);
      try {
        const data = await clientsApi.getGalleryPhotosBySet(username, slug, 1, setId, token);
        if (requestId !== activeSetRequestId.current) return;
        setPhotos(data.results || []);
        setPhotosHasMore(Boolean(data.next));
        nextPageRef.current = 2;
      } catch {
        if (requestId !== activeSetRequestId.current) return;
        setPhotos([]);
        setPhotosHasMore(false);
        setSetLoadError(true);
      } finally {
        if (requestId === activeSetRequestId.current) {
          setPhotosLoadingSet(false);
        }
      }
    },
    [username, slug, token],
  );

  /**
   * The public gallery uses the same durable `?set=<id>` contract as the
   * photographer workspace. A missing or stale id safely resolves to the
   * first real set; a gallery with no sets continues to use its full feed.
   */
  useEffect(() => {
    if (loading || photoSets.length === 0) return;

    const selectedSet = photoSets.find((set) => set.id === requestedSetId);
    const nextSetId = selectedSet?.id || photoSets[0].id;

    if (requestedSetId !== nextSetId) {
      const params = new URLSearchParams(searchParams);
      params.set("set", nextSetId);
      setSearchParams(params, { replace: true });
    }

    if (activeSetId !== nextSetId) {
      setActiveSetId(nextSetId);
      void loadPhotoSet(nextSetId);
    }
  }, [
    activeSetId,
    loadPhotoSet,
    loading,
    photoSets,
    requestedSetId,
    searchParams,
    setSearchParams,
  ]);

  const handleSelectSet = useCallback(
    (setId) => {
      if (!photoSets.some((set) => set.id === setId) || setId === activeSetId) return;

      // Only update the URL. The sync effect above reacts to it and performs
      // the one load for the new set — doing the load here as well made every
      // tab switch fetch the same page three times (here, the effect seeing
      // the not-yet-updated URL, then the effect again once it caught up).
      const params = new URLSearchParams(searchParams);
      params.set("set", setId);
      setSearchParams(params);
    },
    [activeSetId, photoSets, searchParams, setSearchParams],
  );

  /**
   * Adds/removes one favorite: the heart updates instantly and reverts if the
   * server call fails. Adding sends the visitor's email (and optional name) so
   * the favorite lands in their "My Favorites" list under their email.
   */
  const applyFavorite = async (photoId, wasFavorited, profileOverride = null) => {
    setFavoritedIds((prev) => {
      const next = new Set(prev);
      if (wasFavorited) next.delete(photoId);
      else next.add(photoId);
      return next;
    });

    try {
      const identity = getClientIdentity();
      if (wasFavorited) {
        await clientsApi.removeFavorite(username, slug, photoId, identity);
      } else {
        const profile = profileOverride || useVisitorStore.getState().getProfile(sessionKey);
        await clientsApi.addFavorite(username, slug, photoId, identity, { email: profile?.email, name: profile?.name });
      }
    } catch (err) {
      // Rollback — the optimistic update didn't actually stick server-side.
      setFavoritedIds((prev) => {
        const next = new Set(prev);
        if (wasFavorited) next.add(photoId);
        else next.delete(photoId);
        return next;
      });
      throw err;
    }
  };

  const handleToggleFavorite = async (photoId) => {
    const wasFavorited = favoritedIds.has(photoId);
    if (!wasFavorited) {
      const profile = useVisitorStore.getState().getProfile(sessionKey);
      if (!profile?.email && !serverEmail) {
        // First heart: ask for the email once, then save this photo.
        pendingFavoriteRef.current = photoId;
        setEmailPromptOpen(true);
        return;
      }
    }
    try {
      await applyFavorite(photoId, wasFavorited);
    } catch {
      toast("We couldn't update your favorite. Please try again.", "error");
    }
  };

  const handleFavoriteEmailSubmit = async ({ email, name }) => {
    const photoId = pendingFavoriteRef.current;
    if (photoId) await applyFavorite(photoId, false, { email, name }); // a bad email surfaces inside the prompt
    setVisitorProfile(sessionKey, { email, name }); // remembered only once the server accepted it
    pendingFavoriteRef.current = null;
    setEmailPromptOpen(false);
    toast("Saved to My Favorites", "success");
  };

  // ── Render Path: Loading State ─────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#FDFBF7]">
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
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#FDFBF7] px-6 text-center">
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
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#FDFBF7] px-6 text-center">
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
        className="min-h-screen flex flex-col items-center justify-center px-6 bg-[#FDFBF7]"
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
  const coverSrc = coverUrl || (
    photos.length > 0
      ? (photos[0]?.display_url || photos[0]?.thumbnail_url || photos[0]?.poster_url)
      : null
  );

  return (
    <div className={`min-h-screen ${resolvedDesign.theme.bg}`}>
      {/* ── FULL-BLEED HERO COVER BANNER ──────────────────────────────── */}
      <section className="relative h-screen min-h-screen h-[100svh] w-full overflow-hidden flex-shrink-0">
        {/* Background Image */}
        <div className="absolute inset-0">
          {coverSrc ? (
            <img
              src={coverSrc}
              // The hero is the page's largest paint: give the browser the
              // 1280px tier for phones/small windows and the 2048px tier for
              // wide screens, and fetch it ahead of the grid.
              srcSet={
                coverUrl && coverMediumUrl && coverSrc === coverUrl
                  ? `${coverMediumUrl} 1280w, ${coverUrl} 2048w`
                  : undefined
              }
              sizes="100vw"
              fetchPriority="high"
              decoding="async"
              alt=""
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full"
              style={{ backgroundColor: brandingColor || "#0f172a" }}
            />
          )}
          {/* Overlay keeps the editorial cover readable without introducing a second visual system. */}
          <div className="absolute inset-0 bg-black/35" />
        </div>

        {/* Hero Content */}
        <div className="relative z-10 flex flex-col items-center justify-center h-full px-6 text-center">
          {/* The photographer's logo — the server only sends it while their
              plan includes Branding, so no entitlement logic lives here. */}
          {photographerLogo && !logoFailed && (
            <img
              src={photographerLogo}
              alt={photographerName ? `${photographerName} logo` : "Photographer logo"}
              onError={() => setLogoFailed(true)}
              className="mb-6 max-h-20 max-w-[12rem] object-contain drop-shadow-[0_1px_6px_rgba(0,0,0,0.35)]"
            />
          )}
          {photographerName && (
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.25em] text-white/50 font-light mb-5">
              {photographerName}
            </p>
          )}

          <h1 className={`${resolvedDesign.typographyClass} text-4xl sm:text-5xl md:text-6xl lg:text-7xl text-white font-medium tracking-tight mb-4`}>
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
              onClick={() => document.getElementById("gallery-grid")?.scrollIntoView({ behavior: "smooth" })}
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
        <div className="absolute bottom-5 left-1/2 -translate-x-1/2">
          <div className="w-5 h-8 rounded-full border border-white/20 flex items-start justify-center p-1.5">
            <div className="w-1 h-1 rounded-full bg-white/50 animate-bounce" />
          </div>
        </div>
      </section>

      <section id="gallery-toolbar" className="sticky top-0 z-30 border-b border-ink/10 bg-white">
        <div className="mx-auto flex max-w-[1560px] flex-col gap-3 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="min-w-0">
            {photographerName && (
              <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.22em] text-muted">
                {photographerName}
              </p>
            )}
            <h2 className={`${resolvedDesign.typographyClass} truncate text-2xl ${resolvedDesign.theme.text} sm:text-3xl`}>
              {galleryTitle}
            </h2>
          </div>

          {photoSets.length > 0 && (
            <nav
              className="-mx-4 flex min-w-0 gap-1.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0 lg:flex-1 lg:justify-center"
              aria-label="Photo sets"
            >
              {photoSets.map((set) => (
                <button
                  key={set.id}
                  onClick={() => handleSelectSet(set.id)}
                  className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium tracking-wide transition-colors ${
                    activeSetId === set.id
                      ? "border-brand-green-600 text-ink"
                      : "border-transparent text-muted hover:border-ink/20 hover:text-ink"
                  }`}
                  aria-current={activeSetId === set.id ? "page" : undefined}
                >
                  {set.name} <span className="text-[10px] opacity-70">({set.photo_count})</span>
                </button>
              ))}
            </nav>
          )}

          {photos.length > 0 && (
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => setFavoritesOpen(true)}
                className="rounded p-2 text-slate-600 transition hover:bg-slate-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
                aria-label="View favorites"
                title="Favorites"
              >
                <Heart className="h-5 w-5" />
              </button>
              {allowDownload && (
                <button
                  type="button"
                  onClick={openGalleryDownload}
                  className="rounded p-2 text-slate-600 transition hover:bg-slate-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
                  aria-label="Download gallery"
                  title="Download gallery"
                >
                  <Download className="h-5 w-5" />
                </button>
              )}
              <ShareMenu url={resolveShareUrl(shareUrl, username, slug)} title={galleryTitle} />
              {photos.length > 0 && (
                <button
                  type="button"
                  onClick={openSlideshow}
                  className="rounded p-2 text-slate-600 transition hover:bg-slate-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
                  aria-label="Start slideshow"
                  title="Slideshow"
                >
                  <Play className="h-5 w-5" />
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      {/* ── PHOTO GRID SECTION ────────────────────────────────────────── */}
      <main
        id="gallery-grid"
        className="scroll-mt-36 mx-auto max-w-[1560px] px-3 py-10 sm:px-6 lg:px-8 lg:py-12"
        style={{ animation: "fadeUp 0.5s ease both" }}
      >

        {/* Dynamic Visual Masonry vs Empty State Fallback */}
        {photosLoadingSet ? (
          <GallerySkeleton />
        ) : setLoadError ? (
          <div className="text-center py-24 border border-dashed border-cream-300 rounded-xl bg-white">
            <p className="text-sm text-muted font-light mb-4">We couldn't load these photos.</p>
            <button
              type="button"
              onClick={() => void loadPhotoSet(activeSetId)}
              className="text-xs uppercase tracking-widest text-ink border border-ink/30 px-4 py-2 rounded-full hover:bg-ink/5 transition"
            >
              Try again
            </button>
          </div>
        ) : photos.length === 0 ? (
          <div className="text-center py-24 border border-dashed border-cream-300 rounded-xl bg-white">
            <p className="text-sm text-muted font-light">
              {activeSetId ? "No photos in this set yet." : "No images in this collection yet."}
            </p>
          </div>
        ) : (
          <>
            <PublicMasonryGrid
              photos={photos}
              token={token}
              username={username}
              slug={slug}
              onPhotoClick={setLightboxIndex}
              gridStyle={resolvedDesign.gridStyle}
              thumbSize={resolvedDesign.thumbSize}
              gridSpacing={resolvedDesign.gridSpacing}
              favoritedIds={favoritedIds}
              onToggleFavorite={handleToggleFavorite}
              allowDownload={allowDownload}
              onDownloadPhoto={openPhotoDownload}
            />
            {photosHasMore && (
              <div className="flex justify-center mt-10">
                <button
                  onClick={loadMorePhotos}
                  disabled={loadingMorePhotos}
                  className="text-xs uppercase tracking-widest text-ink border border-ink/30 px-8 py-3 rounded-full hover:bg-ink/5 transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loadingMorePhotos ? "Loading…" : loadMoreError ? "Couldn't load more — try again" : "Load More"}
                </button>
              </div>
            )}
          </>
        )}

        {lightboxIndex !== null && (
          <PhotoLightbox
            photos={photos}
            index={lightboxIndex}
            token={token}
            onClose={() => setLightboxIndex(null)}
            onChange={setLightboxIndex}
            videoAccessToken={token}
            isFavorited={favoritedIds.has(photos[lightboxIndex]?.id)}
            onToggleFavorite={handleToggleFavorite}
            onDownload={allowDownload ? openPhotoDownload : undefined}
          />
        )}

        {slideshowIndex !== null && (
          <PhotoLightbox
            photos={photos}
            index={slideshowIndex}
            token={token}
            onClose={() => {
              setSlideshowIndex(null);
              setSlideshowAutoplay(false);
            }}
            onChange={setSlideshowIndex}
            videoAccessToken={token}
            isFavorited={favoritedIds.has(photos[slideshowIndex]?.id)}
            onToggleFavorite={handleToggleFavorite}
            onDownload={allowDownload ? openPhotoDownload : undefined}
            slideshowMode={slideshowAutoplay}
          />
        )}

        <FavoriteEmailModal
          open={emailPromptOpen}
          onClose={() => { pendingFavoriteRef.current = null; setEmailPromptOpen(false); }}
          onSubmit={handleFavoriteEmailSubmit}
          galleryTitle={galleryTitle}
          photographerName={photographerName}
          initialEmail={visitorProfile?.email || ""}
          initialName={visitorProfile?.name || ""}
        />

        <FavoritesPanel
          open={favoritesOpen}
          onClose={() => setFavoritesOpen(false)}
          username={username}
          slug={slug}
          identity={getClientIdentity()}
          galleryTitle={galleryTitle}
          photographerName={photographerName}
          profile={visitorProfile}
          onChanged={() => loadFavorites(token, getClientIdentity())}
        />

        <DownloadModal
          open={downloadTarget !== null}
          onClose={() => setDownloadTarget(null)}
          username={username}
          slug={slug}
          galleryToken={token}
          galleryTitle={galleryTitle}
          photographerName={photographerName}
          hasDownloadPin={hasDownloadPin}
          downloadPolicy={downloadPolicy}
          target={downloadTarget}
          photoSets={photoSets}
          photoCount={photosCount}
        />
      </main>

      {/* Footer */}
      <footer className="text-center py-8 text-xs text-muted border-t border-cream-200 mt-12">
        Delivered via <span className="font-serif text-sm text-ink">Kyapture</span>
      </footer>
    </div>
  );
}
