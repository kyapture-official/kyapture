// frontend/src/pages/dashboard/GalleryPhotosPage.jsx

import { useState, useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import { photosApi } from "../../api/photosApi";
import { mockGalleries } from "../../utils/mockGalleries";
import Spinner from "../../components/ui/Spinner";
import DropZone from "../../components/ui/DropZone";
import PhotoGrid from "../../components/shared/PhotoGrid";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

/**
 * WHAT: The "Photos" child view of the collection workspace.
 * WHY:  Reads gallery/slug from the parent layout via useOutletContext()
 *       instead of fetching or receiving them as props — this is what
 *       makes it a true child route rather than a standalone page.
 */
export default function GalleryPhotosPage() {
  const { gallery, slug, isMountedRef } = useOutletContext();

  const [photos, setPhotos] = useState([]);
  const [photosLoading, setPhotosLoading] = useState(true);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  const blobUrlsRef = useRef([]); // preview blob: URLs still awaiting revocation

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
                      thumbnail_url:
                        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
                    },
                    {
                      id: "mock-img-2",
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

  // ── UPLOAD ───────────────────────────────────────────────────────────────
  const handleFilesSelected = async (files) => {
    if (!files?.length) return;

    if (USE_MOCK_DATA) {
      const queueItems = files.map((file) => {
        const previewUrl = URL.createObjectURL(file);
        blobUrlsRef.current.push(previewUrl);
        return {
          id: Math.random().toString(36).slice(2, 9),
          file,
          previewUrl,
          progress: 0,
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
                  thumbnail_url: item.previewUrl,
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
      };
    });
    setUploadQueue((prev) => [...prev, ...queueItems]);

    for (const item of queueItems) {
      const formData = new FormData();
      formData.append("image", item.file);

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

        // Revoke immediately on success — PhotoGrid now renders from the
        // server's thumbnail_url, so the local blob preview is unused.
        URL.revokeObjectURL(item.previewUrl);
        blobUrlsRef.current = blobUrlsRef.current.filter(
          (u) => u !== item.previewUrl,
        );
      } catch (err) {
        if (isMountedRef.current) {
          setUploadQueue((prev) =>
            prev.map((q) => (q.id === item.id ? { ...q, error: true } : q)),
          );
          setErrorMsg(
            err.response?.data?.image?.[0] ||
              `Failed to upload ${item.file.name}.`,
          );
        }
        // NOT revoked here — the failed row stays visible so the user can
        // see which photo failed. Revoked on dismiss instead (below), or by
        // the unmount safety net above if they navigate away first.
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
      await photosApi.deletePhotos([photoId]);
    } catch {
      if (isMountedRef.current) {
        setPhotos(originalPhotos); // restore exact original order on failure
        setErrorMsg("Failed to delete photo. Please try again.");
      }
    }
  };

  // ── RENDER ───────────────────────────────────────────────────────────────
  return (
    <div className="bg-white rounded-2xl border border-cream-200 shadow-sm p-6">
      <h2 className="text-base font-semibold text-ink mb-2 border-b border-cream-100 pb-3">
        Photo Management
      </h2>
      <p className="text-xs text-muted mb-6">
        Upload multiple images to populate this collection. Once uploaded,
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

      <DropZone onFiles={handleFilesSelected} disabled={photosLoading} />

      {uploadQueue.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploadQueue.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 p-2 rounded-lg bg-cream-50"
            >
              <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 bg-cream-200">
                <img
                  src={item.previewUrl}
                  alt=""
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex-1">
                <div className="text-xs text-ink/70 truncate">
                  {item.file.name}
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
          <PhotoGrid photos={photos} onDelete={handleDeletePhoto} showActions />
        )}
      </div>
    </div>
  );
}
