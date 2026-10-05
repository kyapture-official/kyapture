// frontend/src/pages/dashboard/GalleryPhotosPage.jsx

import { galleriesApi } from "../../api/galleriesApi";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { photosApi } from "../../api/photosApi";
import { subscriptionsApi } from "../../api/subscriptionsApi";
import Spinner from "../../components/ui/Spinner";
import DropZone from "../../components/ui/DropZone";
import PhotoGrid from "../../components/shared/PhotoGrid";
import ConfirmDialog from "../../components/shared/ConfirmDialog";
import PlanLimitModal from "../../components/shared/PlanLimitModal";
import { usePlanUsage } from "../../hooks/usePlanUsage";
import {
  cheapestVideoPlan,
  checkVideoBatch,
  isVideoFile,
  videoLimitFromError,
} from "../../utils/planLimitFlow";
import { readVideoDuration } from "../../utils/videoDuration";
import { formatVideoMinutes } from "../../utils/planLimits";
import { ArrowDownWideNarrow, Check, LayoutGrid, PlusCircle } from "lucide-react";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_INTERVAL_MS = 15000;
const MAX_POLL_ATTEMPTS = 100;

// The picker always offers video: whether the plan allows it is the server's
// answer (usage endpoint), shown as a modal when a video is chosen.
const ACCEPTED_FILES = "image/*,video/mp4,video/quicktime,video/x-m4v";

// View-only sorting of the set already loaded in the grid. "custom" is the
// server order (upload order plus any drag-reorder) and is the only mode where
// drag-reorder is offered, so a reorder always saves what the photographer sees.
const SORT_OPTIONS = [
  { key: "custom", label: "Custom order" },
  { key: "name-asc", label: "Filename A–Z" },
  { key: "name-desc", label: "Filename Z–A" },
  { key: "date-desc", label: "Newest uploads first" },
  { key: "date-asc", label: "Oldest uploads first" },
];

const byName = (a, b) =>
  String(a.original_name || "").localeCompare(String(b.original_name || ""), undefined, { numeric: true, sensitivity: "base" });
const byDate = (a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0);

const sortPhotos = (photos, sortKey) => {
  switch (sortKey) {
    case "name-asc": return [...photos].sort(byName);
    case "name-desc": return [...photos].sort((a, b) => byName(b, a));
    case "date-asc": return [...photos].sort(byDate);
    case "date-desc": return [...photos].sort((a, b) => byDate(b, a));
    default: return photos;
  }
};

const getErrorMessage = (error, fallback) => {
  const data = error?.response?.data;
  const message =
    data?.image?.[0] ||
    data?.video?.[0] ||
    data?.message ||
    data?.error ||
    (typeof data === "string" ? data : null) ||
    error?.message;

  return typeof message === "string" && !/<[^>]+>/.test(message)
    ? message
    : fallback;
};

/** The Photos child route for a gallery workspace. */
export default function GalleryPhotosPage() {
  const {
    gallery,
    setGallery,
    slug,
    isMountedRef,
    sets,
    setsLoading,
    refreshSets,
    activeSetId,
  } = useOutletContext();
  const { usage, refresh: refreshUsage } = usePlanUsage();
  const [videoLimit, setVideoLimit] = useState(null); // why video was refused: { code, used_minutes, plan_limit_minutes, plan_name, videoPlan, photosKept }
  const plansRef = useRef(null);
  const noVideoOnPlan = usage?.video_minutes_limit === 0;

  const [photos, setPhotos] = useState([]);
  const [photosLoading, setPhotosLoading] = useState(true);
  const [uploadQueue, setUploadQueue] = useState([]);
  const uploadQueueRef = useRef([]);
  uploadQueueRef.current = uploadQueue;
  const [errorMsg, setErrorMsg] = useState("");
  const [isGridDragging, setIsGridDragging] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // photo awaiting the permanent-delete confirmation
  const [deleting, setDeleting] = useState(false);
  const [sortKey, setSortKey] = useState("custom");
  const [sortOpen, setSortOpen] = useState(false);
  const [tileSize, setTileSize] = useState("medium");
  const sortRef = useRef(null);

  const blobUrlsRef = useRef([]);
  const photosRef = useRef(photos);
  const activeSetIdRef = useRef(activeSetId);
  const fileInputRef = useRef(null);

  const activeSet = useMemo(
    () => sets.find((set) => String(set.id) === String(activeSetId)) || null,
    [activeSetId, sets],
  );
  const acceptedFiles = ACCEPTED_FILES;

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

  useEffect(() => {
    activeSetIdRef.current = activeSetId;
  }, [activeSetId]);

  // A failed set-list fetch must not leave the content area in its initial
  // loading state forever. Normal background count refreshes deliberately do
  // not participate in the photo-fetch effect below, so they never blank or
  // refetch the currently visible set grid.
  useEffect(() => {
    if (!USE_MOCK_DATA && !setsLoading && (!activeSetId || !activeSet)) {
      setPhotosLoading(false);
    }
  }, [activeSet, activeSetId, setsLoading]);

  useEffect(() => {
    if (!sortOpen) return undefined;
    const onPointerDown = (event) => {
      if (!sortRef.current?.contains(event.target)) setSortOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setSortOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [sortOpen]);

  const displayedPhotos = useMemo(() => sortPhotos(photos, sortKey), [photos, sortKey]);

  useEffect(() => () => {
    blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  // Keep a missed file drop from navigating the browser away from the
  // workspace while the grid is visible.
  useEffect(() => {
    const preventBrowserOpen = (event) => event.preventDefault();
    window.addEventListener("dragover", preventBrowserOpen);
    window.addEventListener("drop", preventBrowserOpen);
    return () => {
      window.removeEventListener("dragover", preventBrowserOpen);
      window.removeEventListener("drop", preventBrowserOpen);
    };
  }, []);

  // The backend owns the filter. The grid only ever holds the current set,
  // rather than a full gallery with a client-side filter layered on top.
  useEffect(() => {
    if (!USE_MOCK_DATA && (!activeSetId || !activeSet)) {
      setPhotos([]);
      setPhotosLoading(setsLoading);
      return undefined;
    }

    let cancelled = false;

    if (USE_MOCK_DATA) {
      setPhotosLoading(true);
      const timeoutId = window.setTimeout(() => {
        if (!cancelled && isMountedRef.current) {
          setPhotos(
            gallery?.slug === "mila-portraits"
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
      return () => {
        cancelled = true;
        window.clearTimeout(timeoutId);
      };
    }

    const controller = new AbortController();
    setPhotosLoading(true);
    setErrorMsg("");
    void (async () => {
      try {
        const data = await photosApi.list(slug, activeSetId, controller.signal);
        if (!cancelled && isMountedRef.current) setPhotos(data || []);
      } catch (error) {
        if (!controller.signal.aborted && isMountedRef.current) {
          setErrorMsg(getErrorMessage(error, "Failed to load photos for this set."));
        }
      } finally {
        if (!cancelled && isMountedRef.current) setPhotosLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeSet?.id, activeSetId, gallery?.slug, isMountedRef, slug]);

  const hasPendingAssets = useMemo(
    () =>
      photos.some(
        (photo) =>
          photo.processing_status === "pending" ||
          photo.processing_status === "processing",
      ),
    [photos],
  );

  useEffect(() => {
    if (USE_MOCK_DATA || !hasPendingAssets) return undefined;

    let attempts = 0;
    let currentDelay = POLL_INTERVAL_MS;
    let lastPendingIdsKey = "";
    let cancelled = false;
    let timeoutId = null;

    const tick = async () => {
      attempts += 1;
      if (attempts > MAX_POLL_ATTEMPTS) {
        if (isMountedRef.current) {
          setErrorMsg(
            "Some items are still processing in the background — this is taking longer than usual. Refresh the page in a bit to check on them.",
          );
        }
        return;
      }

      const pendingAssets = photosRef.current.filter(
        (photo) =>
          photo.processing_status === "pending" ||
          photo.processing_status === "processing",
      );
      if (pendingAssets.length === 0) return;

      const pendingIds = pendingAssets.map((photo) => photo.id);
      const pendingIdsKey = [...pendingIds].sort().join(",");
      if (pendingIdsKey !== lastPendingIdsKey) {
        currentDelay = POLL_INTERVAL_MS;
        lastPendingIdsKey = pendingIdsKey;
      }

      let anyTransitioned = false;
      try {
        const results = await photosApi.getStatusBatch(slug, pendingIds);
        if (!isMountedRef.current || cancelled) return;

        const updatesById = new Map();
        (results || []).forEach((asset) => updatesById.set(asset.id, asset));
        if (updatesById.size > 0) {
          setPhotos((previous) =>
            previous.map((photo) => {
              if (!updatesById.has(photo.id)) return photo;
              const updated = updatesById.get(photo.id);
              if (
                (photo.processing_status === "pending" ||
                  photo.processing_status === "processing") &&
                updated.processing_status !== photo.processing_status
              ) {
                anyTransitioned = true;
              }
              return { ...photo, ...updated };
            }),
          );
        }

        currentDelay = anyTransitioned
          ? POLL_INTERVAL_MS
          : Math.min(currentDelay * 2, POLL_MAX_INTERVAL_MS);
      } catch {
        currentDelay = Math.min(currentDelay * 2, POLL_MAX_INTERVAL_MS);
      }

      if (!cancelled) timeoutId = window.setTimeout(tick, currentDelay);
    };

    timeoutId = window.setTimeout(tick, currentDelay);
    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [activeSetId, hasPendingAssets, isMountedRef, slug]);

  // Opens the shared limit modal for a video refusal. "Not in plan" also names
  // the cheapest plan that has video (plans API), read before the modal opens so
  // its text never changes under the user.
  const showVideoLimit = async (info) => {
    let videoPlan = null;
    if (info.code === "video_not_in_plan") {
      try {
        if (!plansRef.current) plansRef.current = await subscriptionsApi.getPlans();
        videoPlan = cheapestVideoPlan(plansRef.current?.results || plansRef.current);
      } catch {
        // Without the plans list the modal just doesn't name a plan.
      }
    }
    if (isMountedRef.current) setVideoLimit({ ...info, videoPlan });
  };

  const handleFilesSelected = async (selectedFiles) => {
    let files = Array.from(selectedFiles || []);
    if (!files.length) return;

    if (!USE_MOCK_DATA && !activeSetId) {
      setErrorMsg("Choose a photo set before uploading media.");
      return;
    }

    // Videos are checked BEFORE anything uploads: the browser reads each one's
    // length, the server (pre-flight, same rule as the upload) says whether the
    // batch fits the plan. A refusal drops the videos and explains it in the
    // shared limit modal; the rest of the batch (photos) uploads as usual.
    if (!USE_MOCK_DATA && files.some(isVideoFile)) {
      const { allowed, block } = await checkVideoBatch(files, {
        readDuration: readVideoDuration,
        preflight: (count, durations) => photosApi.videoPreflight(count, durations),
      });
      if (block) {
        const fresh = await refreshUsage();
        showVideoLimit({ ...block, plan_name: fresh?.plan_name ?? usage?.plan_name, photosKept: allowed.length });
        files = allowed;
        if (!files.length) return;
      }
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
        setId: activeSetId,
      };
    });
    setUploadQueue((previous) => [...previous, ...queueItems]);

    if (USE_MOCK_DATA) {
      queueItems.forEach((item) => {
        let progress = 0;
        const interval = window.setInterval(() => {
          progress += Math.floor(Math.random() * 15) + 5;
          if (progress >= 100) {
            window.clearInterval(interval);
            if (isMountedRef.current) {
              setPhotos((previous) => [
                ...previous,
                {
                  id: item.id,
                  media_type: item.isVideo ? "video" : "image",
                  thumbnail_url: item.isVideo ? null : item.previewUrl,
                  poster_url: item.isVideo ? null : undefined,
                  original_name: item.file.name,
                },
              ]);
              setUploadQueue((previous) => previous.filter((queueItem) => queueItem.id !== item.id));
            }
          } else if (isMountedRef.current) {
            setUploadQueue((previous) =>
              previous.map((queueItem) =>
                queueItem.id === item.id ? { ...queueItem, progress } : queueItem,
              ),
            );
          }
        }, 300);
      });
      return;
    }

    let uploadedAtLeastOne = false;

    for (const item of queueItems) {
      if (await uploadQueueItem(item)) uploadedAtLeastOne = true;
    }

    if (uploadedAtLeastOne) {
      refreshSets().catch(() => {
        // The upload succeeded; leave the visible grid intact if only the
        // follow-up count refresh has a transient failure.
      });
    }
  };

  /**
   * Uploads ONE queued file into the set it was queued for. Shared by the
   * initial batch and by per-file Retry, so a retry behaves exactly like the
   * first attempt. Resolves true on success; on failure the row stays in the
   * queue with its own error message and a Retry button (the shared banner
   * is only a summary, not the only place the reason shows up).
   */
  const uploadQueueItem = async (item) => {
    const formData = new FormData();
    formData.append(item.isVideo ? "video" : "image", item.file);
    formData.append("set_id", item.setId);

    try {
      const uploaded = await photosApi.uploadBulk(slug, formData, (progress) => {
        if (isMountedRef.current) {
          setUploadQueue((previous) =>
            previous.map((queueItem) =>
              queueItem.id === item.id ? { ...queueItem, progress } : queueItem,
            ),
          );
        }
      });
      if (isMountedRef.current) {
        const newAssets = Array.isArray(uploaded) ? uploaded : [uploaded];
        if (String(activeSetIdRef.current) === String(item.setId)) {
          setPhotos((previous) => [...previous, ...newAssets]);
        }
        setUploadQueue((previous) => previous.filter((queueItem) => queueItem.id !== item.id));
      }

      URL.revokeObjectURL(item.previewUrl);
      blobUrlsRef.current = blobUrlsRef.current.filter((url) => url !== item.previewUrl);
      return true;
    } catch (error) {
      // Fallback if the click-time check was bypassed or stale: the server's own refusal.
      const refusal = error?.response?.status === 403 ? videoLimitFromError(error.response.data) : null;
      if (refusal) {
        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter((url) => url !== item.previewUrl);
        if (isMountedRef.current) {
          setUploadQueue((previous) => previous.filter((queueItem) => queueItem.id !== item.id));
          showVideoLimit({ ...refusal, plan_name: usage?.plan_name });
          refreshUsage();
        }
        return false;
      }
      const message = getErrorMessage(error, `Failed to upload ${item.file.name}.`);
      if (isMountedRef.current) {
        setUploadQueue((previous) =>
          previous.map((queueItem) =>
            queueItem.id === item.id
              ? { ...queueItem, error: true, errorMessage: message }
              : queueItem,
          ),
        );
        setErrorMsg(message);
      }
      return false;
    }
  };

  const handleRetryFailed = async (itemId) => {
    const item = uploadQueueRef.current.find((queueItem) => queueItem.id === itemId);
    if (!item || !item.error) return;
    setErrorMsg("");
    setUploadQueue((previous) =>
      previous.map((queueItem) =>
        queueItem.id === itemId
          ? { ...queueItem, error: false, errorMessage: undefined, progress: 0 }
          : queueItem,
      ),
    );
    if (await uploadQueueItem(item)) {
      refreshSets().catch(() => {});
    }
  };

  const handleDismissFailed = (itemId) => {
    setUploadQueue((previous) => {
      const item = previous.find((queueItem) => queueItem.id === itemId);
      if (item) {
        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter((url) => url !== item.previewUrl);
      }
      return previous.filter((queueItem) => queueItem.id !== itemId);
    });
  };

  const handleDeletePhoto = async (photoId) => {
    const originalPhotos = photos;
    const photo = originalPhotos.find((item) => item.id === photoId);
    const setIdWhenDeleting = activeSetId;
    setPhotos((previous) => previous.filter((item) => item.id !== photoId));

    if (photo?.thumbnail_url?.startsWith("blob:")) {
      URL.revokeObjectURL(photo.thumbnail_url);
      blobUrlsRef.current = blobUrlsRef.current.filter((url) => url !== photo.thumbnail_url);
    }
    if (USE_MOCK_DATA) return;

    try {
      const { failed } = await photosApi.deletePhotos(slug, [photoId]);
      if (failed.length > 0) {
        if (
          isMountedRef.current &&
          String(activeSetIdRef.current) === String(setIdWhenDeleting)
        ) {
          setPhotos(originalPhotos);
          setErrorMsg("Failed to delete photo. Please try again.");
        }
        return;
      }
      refreshSets().catch(() => {});
    } catch {
      if (
        isMountedRef.current &&
        String(activeSetIdRef.current) === String(setIdWhenDeleting)
      ) {
        setPhotos(originalPhotos);
        setErrorMsg("Failed to delete photo. Please try again.");
      }
    }
  };

  // Permanent delete is always confirmed first; nothing is sent until the confirm button.
  const confirmDeletePhoto = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    try {
      await handleDeletePhoto(pendingDelete.id);
    } finally {
      if (isMountedRef.current) {
        setDeleting(false);
        setPendingDelete(null);
      }
    }
  };

  // The heart: the photographer's own favorite. Optimistic, rolled back on failure.
  // It has nothing to do with the cover.
  const handleToggleFavorite = async (photo) => {
    const next = !photo.is_favorite;
    const apply = (value) =>
      setPhotos((previous) => previous.map((item) => (item.id === photo.id ? { ...item, is_favorite: value } : item)));
    apply(next);
    if (USE_MOCK_DATA) return;
    try {
      await photosApi.setFavorite(photo.id, next);
    } catch {
      if (isMountedRef.current) {
        apply(!next);
        setErrorMsg("Failed to update the favorite. Please try again.");
      }
    }
  };

  const handleMoveToSet = async (photo, targetSetId) => {
    const setIdWhenMoving = activeSetId;
    try {
      await photosApi.assignPhotosToSet(slug, targetSetId, [photo.id]);
      if (isMountedRef.current && String(activeSetIdRef.current) === String(setIdWhenMoving)) {
        setPhotos((previous) => previous.filter((item) => item.id !== photo.id));
      }
      refreshSets().catch(() => {});
    } catch {
      if (isMountedRef.current) setErrorMsg("Failed to move the photo. Please try again.");
    }
  };

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
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  const handleSetCover = async (photoId) => {
    try {
      const updated = await galleriesApi.updateGallery(slug, { cover_photo: photoId });
      if (isMountedRef.current) {
        setGallery((previous) => ({ ...previous, cover_url: updated.cover_url }));
      }
    } catch {
      if (isMountedRef.current) {
        setErrorMsg("Failed to set cover photo. Please try again.");
      }
    }
  };

  // The reorder API requires every asset in full-gallery order. The grid is
  // server-filtered to one set, so obtain the authoritative full ordering and
  // replace only the current set's slots before persisting it.
  const handleReorder = async (orderedIds) => {
    const previousPhotos = photos;
    const setIdWhenReordered = activeSetId;
    const photoMap = new Map(previousPhotos.map((photo) => [photo.id, photo]));
    const reorderedPhotos = orderedIds.map((id) => photoMap.get(id)).filter(Boolean);
    setPhotos(reorderedPhotos);
    if (USE_MOCK_DATA) return;

    try {
      const allPhotos = await photosApi.list(slug);
      const reorderedIdsByString = new Set(orderedIds.map(String));
      let nextReorderedIndex = 0;
      const fullOrderedIds = allPhotos.map((photo) => {
        if (!reorderedIdsByString.has(String(photo.id))) return photo.id;
        const nextId = orderedIds[nextReorderedIndex];
        nextReorderedIndex += 1;
        return nextId;
      });

      if (nextReorderedIndex !== orderedIds.length) {
        throw new Error("The set changed before its new order could be saved.");
      }

      await photosApi.reorderPhotos(slug, fullOrderedIds);
    } catch {
      if (
        isMountedRef.current &&
        String(activeSetIdRef.current) === String(setIdWhenReordered)
      ) {
        setPhotos(previousPhotos);
        setErrorMsg("Failed to save the new order. Please try again.");
      }
    }
  };

  const openFilePicker = () => fileInputRef.current?.click();

  const handleFileInputChange = (event) => {
    handleFilesSelected(event.target.files);
    event.target.value = "";
  };

  const isFileDrag = (event) => event.dataTransfer?.types?.includes("Files");

  const handleGridDragEnter = (event) => {
    if (!isFileDrag(event) || photosLoading) return;
    event.preventDefault();
    setIsGridDragging(true);
  };

  const handleGridDragOver = (event) => {
    if (!isFileDrag(event) || photosLoading) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };

  const handleGridDragLeave = (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setIsGridDragging(false);
  };

  const handleGridDrop = (event) => {
    if (!isFileDrag(event) || photosLoading) return;
    event.preventDefault();
    setIsGridDragging(false);
    handleFilesSelected(event.dataTransfer.files);
  };

  return (
    <div>
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 className="min-w-0 truncate text-xl font-semibold text-ink md:text-2xl">
          {activeSet?.name || (setsLoading ? "Loading photo set…" : "Photos")}
        </h2>
        <div className="flex flex-shrink-0 items-center gap-1 sm:gap-2">
          <div className="relative" ref={sortRef}>
            <button
              type="button"
              onClick={() => setSortOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={sortOpen}
              aria-label="Sort photos"
              title="Sort photos"
              className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
                sortKey === "custom" ? "text-muted" : "text-brand-green-600"
              }`}
            >
              <ArrowDownWideNarrow className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
            </button>
            {sortOpen && (
              <div
                role="menu"
                aria-label="Sort photos"
                className="absolute right-0 top-full z-30 mt-1 w-52 overflow-hidden rounded-xl border border-cream-200 bg-white py-1 shadow-card"
              >
                {SORT_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    role="menuitemradio"
                    aria-checked={sortKey === option.key}
                    onClick={() => {
                      setSortKey(option.key);
                      setSortOpen(false);
                    }}
                    className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2.5 text-left text-xs text-ink hover:bg-cream-100 focus:bg-cream-100 focus:outline-none"
                  >
                    {option.label}
                    {sortKey === option.key && <Check className="h-3.5 w-3.5 text-brand-green-600" aria-hidden="true" />}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setTileSize((size) => (size === "medium" ? "large" : "medium"))}
            aria-pressed={tileSize === "large"}
            aria-label={tileSize === "large" ? "Show smaller thumbnails" : "Show larger thumbnails"}
            title={tileSize === "large" ? "Smaller thumbnails" : "Larger thumbnails"}
            className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
              tileSize === "large" ? "text-brand-green-600" : "text-muted"
            }`}
          >
            <LayoutGrid className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </button>
          <span className="mx-1 hidden h-5 w-px bg-cream-200 sm:block" aria-hidden="true" />
          <button
            type="button"
            onClick={openFilePicker}
            disabled={photosLoading || (!USE_MOCK_DATA && !activeSetId)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-2 text-sm font-medium text-brand-green-600 hover:text-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PlusCircle className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
            Add Media
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedFiles}
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />

      {errorMsg && (
        <div role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {!photosLoading && (USE_MOCK_DATA || activeSetId) && photos.length === 0 && (
        <DropZone
          onFiles={handleFilesSelected}
          disabled={photosLoading}
          accept={acceptedFiles}
          label="Add media to this photo set"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-cream-200 bg-cream-100">
            <svg className="h-6 w-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2H6a2 2 0 01-2-2V6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-ink">Drop photos or videos here</p>
            <p className="mt-1 text-xs text-muted">
              {noVideoOnPlan
                ? "or click to browse — JPG, PNG, WEBP (video requires a paid plan)"
                : "or click to browse — JPG, PNG, WEBP, MP4, MOV"}
            </p>
          </div>
        </DropZone>
      )}

      {uploadQueue.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploadQueue.map((item) => (
            <div key={item.id} className="flex items-center gap-3 rounded-lg bg-cream-100 p-2">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded bg-cream-300">
                {item.isVideo ? (
                  <svg className="h-4 w-4 text-ink/50" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                ) : (
                  <img src={item.previewUrl} alt="" className="h-full w-full object-cover" />
                )}
              </div>
              <div className="flex-1">
                <div className="truncate text-xs text-ink/70">
                  {item.file.name}
                  {item.isVideo && <span className="ml-1.5 text-[9px] uppercase tracking-wide text-muted">Video</span>}
                </div>
                {item.error && item.errorMessage && (
                  <div className="mt-0.5 truncate text-[10px] text-red-600" title={item.errorMessage}>
                    {item.errorMessage}
                  </div>
                )}
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-cream-300">
                  <div className={`h-full rounded-full transition-all ${item.error ? "bg-red-400" : "bg-ink"}`} style={{ width: `${item.error ? 100 : item.progress}%` }} />
                </div>
              </div>
              {item.error ? (
                <div className="flex flex-shrink-0 items-center gap-2 text-[10px] font-medium">
                  <button type="button" onClick={() => handleRetryFailed(item.id)} className="cursor-pointer text-ink hover:underline">
                    Retry
                  </button>
                  <button type="button" onClick={() => handleDismissFailed(item.id)} className="cursor-pointer text-red-600 hover:text-red-700">
                    Dismiss
                  </button>
                </div>
              ) : (
                // At 100% the bytes are sent but the server is still saving the
                // file and queuing processing — say so instead of a frozen "100%".
                <span className="flex-shrink-0 text-[10px] text-muted">
                  {item.progress >= 100 ? "Finalizing…" : `${item.progress}%`}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-4">
        {photosLoading || (!USE_MOCK_DATA && setsLoading) ? (
          <div className="flex justify-center py-16"><Spinner size="lg" /></div>
        ) : !USE_MOCK_DATA && !activeSetId ? (
          <p className="py-16 text-center text-sm text-muted">No photo set is available for this gallery.</p>
        ) : photos.length > 0 ? (
          <div
            onDragEnter={handleGridDragEnter}
            onDragOver={handleGridDragOver}
            onDragLeave={handleGridDragLeave}
            onDrop={handleGridDrop}
            className={isGridDragging ? "rounded-xl ring-2 ring-brand-green-400 ring-offset-2" : ""}
          >
            <PhotoGrid
              photos={displayedPhotos}
              tileSize={tileSize}
              onDelete={setPendingDelete}
              onSetCover={handleSetCover}
              onReorder={sortKey === "custom" ? handleReorder : undefined}
              onDownload={handleDownload}
              onToggleFavorite={handleToggleFavorite}
              onMoveToSet={handleMoveToSet}
              sets={sets}
              activeSetId={activeSetId}
              showActions
            />
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this photo permanently?"
        confirmLabel="Delete permanently"
        busy={deleting}
        onConfirm={confirmDeletePhoto}
        onCancel={() => setPendingDelete(null)}
      >
        <p>
          <span className="font-medium text-ink">{pendingDelete?.original_name || "This photo"}</span> and every stored copy of it
          (original, download and preview files) will be removed for good, and it will stop counting toward your storage.
          This cannot be undone.
        </p>
      </ConfirmDialog>

      <PlanLimitModal
        open={videoLimit !== null}
        title={videoLimit?.code === "video_not_in_plan" ? "Video upload is available on a paid plan" : "Video minutes limit reached"}
        onClose={() => setVideoLimit(null)}
      >
        {videoLimit?.code === "video_not_in_plan" ? (
          <p>
            Your <span className="font-medium text-ink">{videoLimit.plan_name || "current"}</span> plan doesn&apos;t include video.
            {videoLimit.videoPlan && (
              <>
                {" "}
                <span className="font-medium text-ink">{videoLimit.videoPlan.name}</span> includes{" "}
                {videoLimit.videoPlan.video_minutes == null
                  ? "unlimited video"
                  : `${formatVideoMinutes(videoLimit.videoPlan.video_minutes)} of video`}.
              </>
            )}
            {videoLimit.photosKept > 0 &&
              ` The other ${videoLimit.photosKept} file${videoLimit.photosKept === 1 ? " is" : "s are"} uploading.`}
          </p>
        ) : (
          <p>
            You have used{" "}
            <span className="font-medium text-ink" data-testid="video-limit-count">
              {videoLimit?.used_minutes} / {videoLimit?.plan_limit_minutes} min
            </span>{" "}
            of video{videoLimit?.plan_name ? <> on your <span className="font-medium text-ink">{videoLimit.plan_name}</span> plan</> : ""}.
            {videoLimit?.upload_minutes != null && (
              <>
                {" "}This upload adds{" "}
                <span className="font-medium text-ink" data-testid="video-limit-batch">{videoLimit.upload_minutes} min</span>.
              </>
            )}{" "}
            Delete a video or view plans to upgrade.
            {videoLimit?.photosKept > 0 &&
              ` The other ${videoLimit.photosKept} file${videoLimit.photosKept === 1 ? " is" : "s are"} uploading.`}
          </p>
        )}
      </PlanLimitModal>
    </div>
  );
}
