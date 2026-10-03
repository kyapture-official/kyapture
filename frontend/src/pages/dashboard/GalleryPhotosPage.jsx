// frontend/src/pages/dashboard/GalleryPhotosPage.jsx

import { galleriesApi } from "../../api/galleriesApi";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { photosApi } from "../../api/photosApi";
import Spinner from "../../components/ui/Spinner";
import DropZone from "../../components/ui/DropZone";
import PhotoGrid from "../../components/shared/PhotoGrid";
import { useSubscription } from "../../hooks/useSubscription";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_INTERVAL_MS = 15000;
const MAX_POLL_ATTEMPTS = 100;

const isVideoFile = (file) => file.type.startsWith("video/");

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
  const { limits } = useSubscription();
  const allowVideo = limits.allow_video;

  const [photos, setPhotos] = useState([]);
  const [photosLoading, setPhotosLoading] = useState(true);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");
  const [isGridDragging, setIsGridDragging] = useState(false);

  const blobUrlsRef = useRef([]);
  const photosRef = useRef(photos);
  const activeSetIdRef = useRef(activeSetId);
  const fileInputRef = useRef(null);

  const activeSet = useMemo(
    () => sets.find((set) => String(set.id) === String(activeSetId)) || null,
    [activeSetId, sets],
  );
  const acceptedFiles = allowVideo
    ? "image/*,video/mp4,video/quicktime,video/x-m4v"
    : "image/*";

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

  const handleFilesSelected = async (selectedFiles) => {
    let files = Array.from(selectedFiles || []);
    if (!files.length) return;

    if (!USE_MOCK_DATA && !activeSetId) {
      setErrorMsg("Choose a photo set before uploading media.");
      return;
    }

    if (!allowVideo) {
      const videoCount = files.filter(isVideoFile).length;
      if (videoCount > 0) {
        files = files.filter((file) => !isVideoFile(file));
        setErrorMsg(
          `Video uploads require an active plan. ${videoCount} video file${
            videoCount > 1 ? "s were" : " was"
          } skipped — upgrade to upload video.`,
        );
      }
      if (!files.length) return;
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

    const uploadSetId = activeSetId;
    let uploadedAtLeastOne = false;

    for (const item of queueItems) {
      const formData = new FormData();
      formData.append(item.isVideo ? "video" : "image", item.file);
      formData.append("set_id", uploadSetId);

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
        uploadedAtLeastOne = true;
        if (isMountedRef.current) {
          const newAssets = Array.isArray(uploaded) ? uploaded : [uploaded];
          if (String(activeSetIdRef.current) === String(uploadSetId)) {
            setPhotos((previous) => [...previous, ...newAssets]);
          }
          setUploadQueue((previous) => previous.filter((queueItem) => queueItem.id !== item.id));
        }

        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter((url) => url !== item.previewUrl);
      } catch (error) {
        if (isMountedRef.current) {
          setUploadQueue((previous) =>
            previous.map((queueItem) =>
              queueItem.id === item.id ? { ...queueItem, error: true } : queueItem,
            ),
          );
          setErrorMsg(getErrorMessage(error, `Failed to upload ${item.file.name}.`));
        }
      }
    }

    if (uploadedAtLeastOne) {
      refreshSets().catch(() => {
        // The upload succeeded; leave the visible grid intact if only the
        // follow-up count refresh has a transient failure.
      });
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
    <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card p-6">
      <div className="mb-6 flex items-center justify-between gap-4 border-b border-cream-200 pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-brand-green-50">
            <svg className="h-5 w-5 text-brand-green-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5z" />
            </svg>
          </div>
          <h2 className="truncate font-serif text-lg text-ink">
            {activeSet?.name || (setsLoading ? "Loading photo set…" : "Photos")}
          </h2>
        </div>
        <button
          type="button"
          onClick={openFilePicker}
          disabled={photosLoading || (!USE_MOCK_DATA && !activeSetId)}
          className="flex-shrink-0 rounded-lg bg-brand-green-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-brand-green-700 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
        >
          + Add Media
        </button>
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
              {allowVideo
                ? "or click to browse — JPG, PNG, WEBP, MP4, MOV"
                : "or click to browse — JPG, PNG, WEBP (video requires a paid plan)"}
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
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-cream-300">
                  <div className={`h-full rounded-full transition-all ${item.error ? "bg-red-400" : "bg-ink"}`} style={{ width: `${item.error ? 100 : item.progress}%` }} />
                </div>
              </div>
              {item.error ? (
                <button type="button" onClick={() => handleDismissFailed(item.id)} className="flex-shrink-0 cursor-pointer text-[10px] font-medium text-red-600 hover:text-red-700">
                  Failed · Dismiss
                </button>
              ) : (
                <span className="flex-shrink-0 text-[10px] text-muted">{item.progress}%</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-6">
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
              photos={photos}
              onDelete={handleDeletePhoto}
              onSetCover={handleSetCover}
              onReorder={handleReorder}
              onDownload={handleDownload}
              showActions
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
