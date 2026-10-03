// File Location: frontend/src/pages/dashboard/FavoritesPage.jsx
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Heart } from "lucide-react";
import { photosApi } from "../../api/photosApi";
import { useToast } from "../../components/ui/Toast";
import Spinner from "../../components/ui/Spinner";
import PhotoLightbox from "../../components/shared/PhotoLightbox";

/**
 * The photographer's Favorites: every photo they hearted in a collection
 * workspace, across all their collections, newest first (Pixieset's "Starred").
 * The heart on a tile un-favorites it and the tile leaves the page.
 */
export default function FavoritesPage() {
  const toast = useToast();
  const [photos, setPhotos] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [lightbox, setLightbox] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const load = useCallback(async (nextPage) => {
    if (nextPage === 1) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const data = await photosApi.listFavorites(nextPage);
      if (!mountedRef.current) return;
      setPhotos((previous) => (nextPage === 1 ? data.results || [] : [...previous, ...(data.results || [])]));
      setHasMore(Boolean(data.next));
      setTotal(data.count || 0);
      setPage(nextPage);
    } catch {
      if (mountedRef.current) setError("We couldn't load your favorites.");
    } finally {
      if (mountedRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    load(1);
  }, [load]);

  const unfavorite = async (photo) => {
    setPhotos((previous) => previous.filter((item) => item.id !== photo.id));
    setTotal((previous) => Math.max(0, previous - 1));
    try {
      await photosApi.setFavorite(photo.id, false);
    } catch {
      if (!mountedRef.current) return;
      setPhotos((previous) => [photo, ...previous]);
      setTotal((previous) => previous + 1);
      toast("Couldn't remove it from your favorites. Please try again.", "error");
    }
  };

  return (
    <div className="mx-auto max-w-6xl animate-fade-up space-y-6">
      <div>
        <h1 className="font-serif text-3xl text-ink md:text-4xl">Favorites</h1>
        <p className="mt-1 text-sm text-muted">
          Photos you&apos;ve hearted in your collections{total > 0 ? ` · ${total}` : ""}.
        </p>
      </div>

      {loading ? (
        <div className="flex h-[40vh] items-center justify-center" role="status" aria-label="Loading favorites">
          <Spinner size="lg" className="text-muted" />
        </div>
      ) : error ? (
        <div role="alert" className="rounded-xl border border-red-100 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700">{error}</p>
          <button
            type="button"
            onClick={() => load(1)}
            className="mt-3 cursor-pointer rounded-lg border border-red-200 bg-white px-4 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Try again
          </button>
        </div>
      ) : photos.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-cream-300 bg-surface-light py-20 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-cream-100">
            <Heart className="h-6 w-6 text-muted" strokeWidth={1.5} aria-hidden="true" />
          </div>
          <p className="text-sm text-ink">No favorites yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-muted">
            Tap the heart on a photo in any collection and it will show up here.
          </p>
        </div>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5" aria-label="Favorite photos">
            {photos.map((photo, index) => (
              <li key={photo.id} className="group relative overflow-hidden rounded-xl bg-cream-100">
                <button
                  type="button"
                  onClick={() => setLightbox(index)}
                  className="block w-full cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
                  aria-label={`View ${photo.original_name || "photo"}`}
                >
                  <img
                    src={photo.thumbnail_url || photo.display_url}
                    alt={photo.original_name || "Favorite photo"}
                    loading="lazy"
                    className="h-48 w-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                </button>
                <button
                  type="button"
                  onClick={() => unfavorite(photo)}
                  aria-label={`Remove ${photo.original_name || "photo"} from favorites`}
                  title="Remove from favorites"
                  className="absolute bottom-10 right-2 z-10 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-white/95 text-red-500 shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
                >
                  <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M12 21s-6.716-4.35-9.428-8.06C.665 10.42 1.1 6.9 3.6 5.1c2.02-1.46 4.63-1.02 6.17.86L12 8.2l2.23-2.24c1.54-1.88 4.15-2.32 6.17-.86 2.5 1.8 2.935 5.32 1.028 7.84C18.716 16.65 12 21 12 21z" />
                  </svg>
                </button>
                <Link
                  to={`/dashboard/galleries/${photo.gallery_slug}`}
                  className="block truncate bg-surface-light px-3 py-2 text-xs text-muted hover:text-ink hover:underline"
                  title={`Open ${photo.gallery_title}`}
                >
                  {photo.gallery_title}
                </Link>
              </li>
            ))}
          </ul>
          {hasMore && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => load(page + 1)}
                disabled={loadingMore}
                className="cursor-pointer rounded-full border border-ink/30 px-6 py-2.5 text-xs uppercase tracking-widest text-ink transition hover:bg-ink/5 disabled:opacity-60"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}

      {lightbox !== null && photos[lightbox] && (
        <PhotoLightbox photos={photos} index={lightbox} onClose={() => setLightbox(null)} onChange={setLightbox} />
      )}
    </div>
  );
}
