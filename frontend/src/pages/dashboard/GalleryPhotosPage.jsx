// frontend/src/pages/dashboard/GalleryPhotosPage.jsx

import { galleriesApi } from "../../api/galleriesApi";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { useOutletContext } from "react-router-dom";
import { photosApi } from "../../api/photosApi";
import { mockGalleries } from "../../utils/mockGalleries";
import Spinner from "../../components/ui/Spinner";
import DropZone from "../../components/ui/DropZone";
import PhotoGrid from "../../components/shared/PhotoGrid";
import { useSubscription } from "../../hooks/useSubscription";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

const isVideoFile = (file) => file.type.startsWith("video/");

// Polling tuning for assets still processing in the background (Celery).
// 3s cadence, capped at 5 minutes total per "session" (i.e. per continuous
// stretch of having at least one pending/processing asset) — long enough
// for a large 4K video on modest worker hardware, short enough that a
// genuinely stuck task (e.g. worker down, ffmpeg missing) doesn't poll
// forever. Applies to images too — they go through the exact same async
// pending→ready window, just usually fast enough not to be noticed.
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 100;

/**
 * WHAT: The "Photos" child view of the collection workspace.
 * WHY:  Reads gallery/slug from the parent layout via useOutletContext()
 *       instead of fetching or receiving them as props — this is what
 *       makes it a true child route rather than a standalone page.
 */
export default function GalleryPhotosPage() {
  const { gallery, setGallery, slug, isMountedRef } = useOutletContext();
  const { limits } = useSubscription();
  const allowVideo = limits.allow_video;

  const [photos, setPhotos] = useState([]);
  const [photosLoading, setPhotosLoading] = useState(true);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  const blobUrlsRef = useRef([]); // preview blob: URLs still awaiting revocation
  const photosRef = useRef(photos);

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

  // Safety net: revoke any leftover blob URLs if the user navigates away
  // mid-upload (e.g. clicks "Settings" while a file is still uploading).

  useEffect(() => {
    return () => {
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  // ── LOAD PHOTOS ──────────────────────────────────────────────────────────
  useEffect(() => {
    async function loadPhotos() {
      setPhotosLoading(true);

      if (USE_MOCK_DATA) {
        setTimeout(() => {
          if (isMountedRef.current) {
            setPhotos(
              gallery.slug === "mila-portraits"
                ? [
                    {
                      id: "mock-img-1",
                      media_type: "image",
                      thumbnail_url:
                        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
                    },
                    {
                      id: "mock-img-2",
                      media_type: "image",
                      thumbnail_url:
                        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=400&q=80",
                    },
                  ]
                : [],
            );
            setPhotosLoading(false);
          }
        }, 300);
        return;
      }

      try {
        const data = await photosApi.list(slug);
        if (isMountedRef.current) setPhotos(data || []);
      } catch {
        if (isMountedRef.current)
          setErrorMsg("Failed to load photos for this collection.");
      } finally {
        if (isMountedRef.current) setPhotosLoading(false);
      }
    }

    loadPhotos();
  }, [slug, gallery.slug, isMountedRef]);

  // ── AUTO-UPDATE PENDING/PROCESSING ASSETS ────────────────────────────────
  // Fixes: video (and, latently, image) thumbnails getting stuck on
  // "Processing…" until a manual refresh. Starts polling whenever any
  // asset in state is still pending/processing, stops the moment none are.
  const hasPendingAssets = useMemo(
    () =>
      photos.some(
        (p) =>
          p.processing_status === "pending" ||
          p.processing_status === "processing",
      ),
    [photos],
  );

  useEffect(() => {
    if (USE_MOCK_DATA) return; // mock mode never sets processing_status='pending'
    if (!hasPendingAssets) return;

    let attempts = 0;

    const intervalId = setInterval(async () => {
      attempts += 1;
      if (attempts > MAX_POLL_ATTEMPTS) {
        clearInterval(intervalId);
        if (isMountedRef.current) {
          setErrorMsg(
            "Some items are still processing in the background — this is taking longer than usual. Refresh the page in a bit to check on them.",
          );
        }
        return;
      }

      const pendingAssets = photosRef.current.filter(
        (p) =>
          p.processing_status === "pending" ||
          p.processing_status === "processing",
      );
      if (pendingAssets.length === 0) return;

      try {
        const results = await Promise.allSettled(
          pendingAssets.map((asset) => photosApi.getById(asset.id)),
        );
        if (!isMountedRef.current) return;

        const updatesById = new Map();
        results.forEach((result) => {
          if (result.status === "fulfilled") {
            updatesById.set(result.value.id, result.value);
          }
        });

        if (updatesById.size > 0) {
          setPhotos((prev) =>
            prev.map((p) =>
              updatesById.has(p.id) ? { ...p, ...updatesById.get(p.id) } : p,
            ),
          );
        }
      } catch {
        // Transient network hiccup — next tick just retries.
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [hasPendingAssets, isMountedRef]);

  // ── UPLOAD ───────────────────────────────────────────────────────────────
  const handleFilesSelected = async (files) => {
    if (!files?.length) return;

    if (!allowVideo) {
      const videoCount = files.filter(isVideoFile).length;
      if (videoCount > 0) {
        files = files.filter((f) => !isVideoFile(f));
        setErrorMsg(
          `Video uploads require an active plan. ${videoCount} video file${
            videoCount > 1 ? "s were" : " was"
          } skipped — upgrade to upload video.`,
        );
      }
      if (!files.length) return;
    }

    if (USE_MOCK_DATA) {
      const queueItems = files.map((file) => {
        const previewUrl = URL.createObjectURL(file);
        blobUrlsRef.current.push(previewUrl);
        return {
          id: Math.random().toString(36).slice(2, 9),
          file,
          previewUrl,
          progress: 0,
          isVideo: isVideoFile(file),
        };
      });
      setUploadQueue((prev) => [...prev, ...queueItems]);
      queueItems.forEach((item) => {
        let progress = 0;
        const interval = setInterval(() => {
          progress += Math.floor(Math.random() * 15) + 5;
          if (progress >= 100) {
            clearInterval(interval);
            if (isMountedRef.current) {
              setPhotos((prev) => [
                ...prev,
                {
                  id: item.id,
                  media_type: item.isVideo ? "video" : "image",
                  thumbnail_url: item.isVideo ? null : item.previewUrl,
                  poster_url: item.isVideo ? null : undefined,
                  original_name: item.file.name,
                },
              ]);
              setUploadQueue((prev) => prev.filter((q) => q.id !== item.id));
            }
          } else if (isMountedRef.current) {
            setUploadQueue((prev) =>
              prev.map((q) => (q.id === item.id ? { ...q, progress } : q)),
            );
          }
        }, 300);
      });
      return;
    }

    const queueItems = files.map((file) => {
      const previewUrl = URL.createObjectURL(file);
      blobUrlsRef.current.push(previewUrl);
      return {
        id: Math.random().toString(36).slice(2, 9),
        file,
        previewUrl,
        progress: 0,
        isVideo: isVideoFile(file),
      };
    });
    setUploadQueue((prev) => [...prev, ...queueItems]);

    for (const item of queueItems) {
      const formData = new FormData();
      formData.append(item.isVideo ? "video" : "image", item.file);

      try {
        const uploaded = await photosApi.uploadBulk(slug, formData, (pct) => {
          if (isMountedRef.current) {
            setUploadQueue((prev) =>
              prev.map((q) => (q.id === item.id ? { ...q, progress: pct } : q)),
            );
          }
        });
        if (isMountedRef.current) {
          const newAssets = Array.isArray(uploaded) ? uploaded : [uploaded];
          setPhotos((prev) => [...prev, ...newAssets]);
          setUploadQueue((prev) => prev.filter((q) => q.id !== item.id));
        }

        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter(
          (u) => u !== item.previewUrl,
        );
      } catch (err) {
        if (isMountedRef.current) {
          setUploadQueue((prev) =>
            prev.map((q) => (q.id === item.id ? { ...q, error: true } : q)),
          );

          const code = err.response?.data?.code;
          if (
            code === "video_upload_requires_subscription" ||
            code === "storage_limit_reached"
          ) {
            setErrorMsg(
              err.response?.data?.message ||
                "Upgrade your plan to continue uploading.",
            );
          } else {
            setErrorMsg(
              err.response?.data?.image?.[0] ||
                err.response?.data?.video?.[0] ||
                err.response?.data?.error ||
                `Failed to upload ${item.file.name}.`,
            );
          }
        }
      }
    }
  };

  const handleDismissFailed = (itemId) => {
    setUploadQueue((prev) => {
      const item = prev.find((q) => q.id === itemId);
      if (item) {
        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter(
          (u) => u !== item.previewUrl,
        );
      }
      return prev.filter((q) => q.id !== itemId);
    });
  };

  // ── DELETE ───────────────────────────────────────────────────────────────
    const handleDeletePhoto = async (photoId) => {
    const originalPhotos = photos;
    const photo = originalPhotos.find((p) => p.id === photoId);

    setPhotos((prev) => prev.filter((p) => p.id !== photoId));

    if (photo?.thumbnail_url?.startsWith("blob:")) {
      URL.revokeObjectURL(photo.thumbnail_url);
      blobUrlsRef.current = blobUrlsRef.current.filter(
        (u) => u !== photo.thumbnail_url,
      );
    }

    if (USE_MOCK_DATA) return;

    try {
      const { failed } = await photosApi.deletePhotos(slug, [photoId]);
      // The bulk endpoint returns 200 even when the id didn't match (wrong
      // gallery/owner, already gone) — that's a logical failure wrapped in
      // a successful response, not a thrown exception, so it must be
      // checked explicitly rather than relying on catch alone.
      if (failed.length > 0 && isMountedRef.current) {
        setPhotos(originalPhotos);
        setErrorMsg("Failed to delete photo. Please try again.");
      }
    } catch {
      if (isMountedRef.current) {
        setPhotos(originalPhotos); // restore exact original order on failure
        setErrorMsg("Failed to delete photo. Please try again.");
      }
    }
  };

  // ── DOWNLOAD (image or video original) ──────────────────────────────────
  // Fetches the original file as a blob and triggers a real "Save As" via a
  // synthetic <a download>. Falls back to window.open when fetch fails —
  // most commonly a CORS block on the S3 origin, since original files are
  // served from S3 in production, not same-origin.
  const handleDownload = async (photo) => {
    const url = photo?.original_url;
    if (!url) {
      setErrorMsg("This file isn't available to download yet.");
      return;
    }

    const filename =
      photo.original_name || (photo.media_type === "video" ? "video" : "photo");

    try {
      const response = await fetch(url, { mode: "cors" });
      if (!response.ok) throw new Error("Network response was not ok");

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
    } catch {
      // Likely a CORS block on the storage origin — open it directly instead.
      // The browser will still download or display it depending on the
      // response headers, which is the best we can do without a proxy.
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  // ── SET COVER (image or video poster) ──────────────────────────────────
  const handleSetCover = async (photoId) => {
    try {
      const updated = await galleriesApi.updateGallery(slug, {
        cover_photo: photoId,
      });
      if (isMountedRef.current) {
        setGallery((prev) => ({ ...prev, cover_url: updated.cover_url }));
      }
    } catch {
      if (isMountedRef.current) {
        setErrorMsg("Failed to set cover photo. Please try again.");
      }
    }
  };

  // ── REORDER ──────────────────────────────────────────────────────────────
  // PhotoGrid does the drag mechanics and array splicing; this is purely
  // persistence — optimistic update first so the drag feels instant, with
  // a rollback to the pre-drag order if the PATCH fails.
  const handleReorder = async (orderedIds) => {
    const previousPhotos = photos;
    const photoMap = new Map(previousPhotos.map((p) => [p.id, p]));
    const reorderedPhotos = orderedIds
      .map((id) => photoMap.get(id))
      .filter(Boolean);
    setPhotos(reorderedPhotos); // optimistic

    if (USE_MOCK_DATA) return;

    try {
      await photosApi.reorderPhotos(slug, orderedIds);
    } catch {
      if (isMountedRef.current) {
        setPhotos(previousPhotos); // rollback
        setErrorMsg("Failed to save the new order. Please try again.");
      }
    }
  };

  // ── RENDER ───────────────────────────────────────────────────────────────
  return (
    <div className="bg-white rounded-2xl border border-cream-200 shadow-sm p-6">
      <h2 className="text-base font-semibold text-ink mb-2 border-b border-cream-100 pb-3">
        Photo & Video Management
      </h2>
      <p className="text-xs text-muted mb-6">
        Upload photos and videos to populate this collection. Once uploaded,
        clients can browse, view in lightbox, and download.
      </p>

      {errorMsg && (
        <div
          role="alert"
          className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700"
        >
          {errorMsg}
        </div>
      )}

      {/* DropZone Update */}
      <DropZone
        onFiles={handleFilesSelected}
        disabled={photosLoading}
        accept={
          allowVideo
            ? "image/*,video/mp4,video/quicktime,video/x-m4v"
            : "image/*"
        }
      >
        <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center border border-gray-300">
          <svg
            className="w-6 h-6 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-gray-900">
            Drop photos or videos here
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {allowVideo
              ? "or click to browse — JPG, PNG, WEBP, MP4, MOV"
              : "or click to browse — JPG, PNG, WEBP (video requires a paid plan)"}
          </p>
        </div>
      </DropZone>

      {uploadQueue.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploadQueue.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 p-2 rounded-lg bg-cream-50"
            >
              <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 bg-cream-200 flex items-center justify-center">
                {item.isVideo ? (
                  <svg
                    className="w-4 h-4 text-ink/50"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
                    />
                  </svg>
                ) : (
                  <img
                    src={item.previewUrl}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                )}
              </div>
              <div className="flex-1">
                <div className="text-xs text-ink/70 truncate">
                  {item.file.name}
                  {item.isVideo && (
                    <span className="ml-1.5 text-[9px] uppercase tracking-wide text-muted">
                      Video
                    </span>
                  )}
                </div>
                <div className="h-1.5 bg-cream-200 rounded-full overflow-hidden mt-1">
                  <div
                    className={`h-full rounded-full transition-all ${item.error ? "bg-red-400" : "bg-ink"}`}
                    style={{ width: `${item.error ? 100 : item.progress}%` }}
                  />
                </div>
              </div>
              {item.error ? (
                <button
                  type="button"
                  onClick={() => handleDismissFailed(item.id)}
                  className="text-[10px] text-red-600 hover:text-red-700 font-medium flex-shrink-0 cursor-pointer"
                >
                  Failed · Dismiss
                </button>
              ) : (
                <span className="text-[10px] text-muted flex-shrink-0">
                  {item.progress}%
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-6">
        {photosLoading ? (
          <div className="py-16 flex justify-center">
            <Spinner size="lg" />
          </div>
        ) : (
          <PhotoGrid
            photos={photos}
            onDelete={handleDeletePhoto}
            onSetCover={handleSetCover}
            onReorder={handleReorder}
            onDownload={handleDownload}
            showActions
          />
        )}
      </div>
    </div>
  );
}
