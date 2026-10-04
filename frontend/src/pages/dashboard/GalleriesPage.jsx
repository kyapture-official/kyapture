// File Location: frontend/src/pages/dashboard/GalleriesPage.jsx
// VERSION: Production-Grade Galleries View — Redesigned UI

import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { useAuthStore } from "../../store/authStore";
import { useToast } from "../../components/ui/Toast";
import { getAlphaBrandingColor } from "../../utils/colorhelper";
import CreateGalleryModal from "../../components/shared/CreateGalleryModal";
import Spinner from "../../components/ui/Spinner";
import ItemMenu from "../../components/shared/ItemMenu";
import ConfirmDialog from "../../components/shared/ConfirmDialog";
import ShareLinkModal from "../../components/shared/ShareLinkModal";
import { resolveShareUrl } from "../../utils/share";

export default function GalleriesPage() {
  const toast = useToast();
  const navigate = useNavigate();

  const username = useAuthStore((s) => s.user?.username);

  const [galleries, setGalleries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [searchTotal, setSearchTotal] = useState(0);
  const [openCreate, setOpenCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [linkGallery, setLinkGallery] = useState(null); // collection whose direct link is shown
  const [pendingDelete, setPendingDelete] = useState(null); // collection awaiting the permanent-delete confirmation
  const [deleting, setDeleting] = useState(false);

  const defaultBrandingColor =
    useAuthStore((s) => s.user?.branding_color) ?? "#111827";

  const [formData, setFormData] = useState({
    title: "",
    branding_color: defaultBrandingColor,
    event_date: "",
  });

  const abortControllerRef = useRef(null);
  const debounceRef = useRef(null);
  const isFirstRunRef = useRef(true);

  const fetchGalleries = useCallback(
    (query, isInitialLoad = false) => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      if (isInitialLoad) setLoading(true);
      else setSearching(true);

      const request = query
        ? galleriesApi
            .searchGalleries(query, controller.signal)
            .then((data) => ({
              list: data.results,
              truncated: data.truncated,
              total: data.count,
            }))
        : galleriesApi.getGalleries({}, controller.signal).then((data) => {
            const list = data?.results || (Array.isArray(data) ? data : []);
            return { list, truncated: false, total: list.length };
          });

      request
        .then(({ list, truncated, total }) => {
          setGalleries(list);
          setSearchTruncated(truncated);
          setSearchTotal(total);
        })
        .catch((err) => {
          if (err.name === "CanceledError" || err.name === "AbortError") return;
          toast(
            query ? "Search failed." : "Failed to load collections.",
            "error",
          );
        })
        .finally(() => {
          if (controller.signal.aborted) return;
          setLoading(false);
          setSearching(false);
        });
    },
    [toast],
  );

  useEffect(() => {
    fetchGalleries("", true);
    return () => abortControllerRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (isFirstRunRef.current) {
      isFirstRunRef.current = false;
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(
      () => fetchGalleries(searchQuery.trim()),
      350,
    );
    return () => clearTimeout(debounceRef.current);
  }, [searchQuery, fetchGalleries]);

  const handleCreateSubmit = async (payload) => {
    const loaderId = toast("Creating your new collection...", "loading");

    try {
      const newGallery = await galleriesApi.createGallery(payload);
      toast.dismiss(loaderId);
      toast("Collection created!", "success");
      setGalleries((prev) => [newGallery, ...prev]);
      setOpenCreate(false);
    } catch (err) {
      toast.dismiss(loaderId);

      if (err.code === 'ERR_NETWORK' && !err.response) {
        toast("Cannot reach the server. Make sure the backend is running on port 8000.", "error");
        throw new Error("Backend unreachable");
      } else if (err.response?.status === 403) {
        const data = err.response?.data;
        const message =
          data?.message ||
          data?.detail ||
          "Upgrade your plan to create more galleries.";
        toast(message, "warning");
        setOpenCreate(false);
        setTimeout(() => navigate("/dashboard/billing"), 2200);
      } else {
        const errorMsg =
          err.response?.data?.error ||
          err.response?.data?.detail ||
          "Failed to create collection.";
        toast(errorMsg, "error");
        throw new Error(errorMsg);
      }
    }
  };

  // "Get direct link": the same link modal the Share dropdown and the collection's three-dot menu use.
  const handleGetLink = (gallery) => {
    if (!resolveShareUrl(username, gallery.slug)) {
      toast("Unable to build link — profile not loaded yet.", "error");
      return;
    }
    setLinkGallery(gallery);
  };

  // Permanent delete — only after the confirm dialog; the card disappears only after the server says it is gone.
  const handleConfirmDelete = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    const loaderId = toast("Deleting collection…", "loading");
    try {
      await galleriesApi.deleteGallery(pendingDelete.slug);
      toast.dismiss(loaderId);
      setGalleries((previous) => previous.filter((item) => item.slug !== pendingDelete.slug));
      setSearchTotal((previous) => Math.max(0, previous - 1));
      toast("Collection permanently deleted.", "success");
      setPendingDelete(null);
    } catch (err) {
      toast.dismiss(loaderId);
      toast(
        err?.response?.status === 404 ? "That collection no longer exists." : "Could not delete the collection. Please try again.",
        "error",
      );
      if (err?.response?.status === 404) {
        setGalleries((previous) => previous.filter((item) => item.slug !== pendingDelete.slug));
        setPendingDelete(null);
      }
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-[60vh] w-full items-center justify-center">
        <Spinner size="lg" className="text-muted" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-fade-up">
      {/* ── HEADER ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl md:text-4xl text-ink">My Collections</h1>
          <p className="text-sm text-muted mt-1">
            Create, manage, and deliver photo collections to your clients.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpenCreate(true)}
          className="sm:self-start inline-flex items-center gap-2 px-5 py-2.5 bg-brand-green-600 hover:bg-brand-green-700 active:scale-[0.98] text-white text-sm font-medium rounded-xl transition-all cursor-pointer shadow-sm hover:shadow-md"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Create Gallery
        </button>
      </div>

      {/* ── SEARCH BAR ── */}
      <div className="relative max-w-md">
        <div className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border transition-all duration-200 ${
          searchFocused
            ? 'border-brand-green-400/40 bg-surface-light shadow-glow-brand ring-2 ring-brand-green-500/10'
            : 'border-cream-200 bg-surface-light hover:border-cream-300'
        }`}>
          <svg
            className="w-4 h-4 text-muted flex-shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="Search collections..."
            aria-label="Search collections"
            className="flex-1 bg-transparent border-none outline-none text-sm text-ink placeholder:text-muted font-sans"
          />
          {searching && (
            <Spinner className="w-4 h-4 text-muted flex-shrink-0" />
          )}
          {!searching && searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              aria-label="Clear search"
              className="text-muted hover:text-ink cursor-pointer text-xs p-0.5 rounded-md hover:bg-cream-100 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* ── TRUNCATION WARNING ── */}
      {searchTruncated && (
        <div className="flex items-center gap-2.5 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 max-w-md">
          <svg className="w-4 h-4 flex-shrink-0 text-amber-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          Showing the first 100 of {searchTotal} matches — refine your search to narrow results.
        </div>
      )}

      {/* ── EMPTY STATE ── */}
      {galleries.length === 0 ? (
        <div className="text-center py-20 bg-surface-light rounded-2xl border-2 border-dashed border-cream-200">
          <div className="w-14 h-14 rounded-full bg-cream-100 flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
            </svg>
          </div>
          <p className="text-sm text-muted font-light mb-4">
            {searchQuery
              ? `No collections match "${searchQuery}".`
              : "No collections yet. Create your first gallery to begin."}
          </p>
          {!searchQuery && (
            <button
              onClick={() => setOpenCreate(true)}
              className="inline-flex items-center gap-2 bg-brand-green-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-brand-green-700 transition-colors cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Create Gallery
            </button>
          )}
        </div>
      ) : (
        /* ── GALLERY GRID ── */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {galleries.map((gallery) => {
            const highlightBg = getAlphaBrandingColor(
              gallery.branding_color,
              "14",
            );

            return (
              <div
                key={gallery.id}
                className="group bg-surface-light border border-cream-200 rounded-2xl overflow-hidden hover:shadow-card-hover hover:border-cream-300 transition-all duration-300 flex flex-col h-full"
              >
                {/* Cover area */}
                <div className="h-44 bg-cream-100 overflow-hidden relative flex-shrink-0">
                  {gallery.cover_url ? (
                    <img
                      src={gallery.cover_url}
                      alt=""
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                    />
                  ) : (
                    <div
                      className="w-full h-full"
                      style={{ backgroundColor: highlightBg }}
                    />
                  )}

                  <ItemMenu
                    className="absolute right-3 top-3 z-10"
                    label={`More actions for ${gallery.title}`}
                    items={[
                      { key: "link", label: "Get direct link", onSelect: () => handleGetLink(gallery) },
                      {
                        key: "preview",
                        label: "Preview",
                        onSelect: () => navigate(`/dashboard/galleries/${gallery.slug}`, { state: { openPreview: true } }),
                      },
                      {
                        key: "edit",
                        label: "Quick edit",
                        onSelect: () => navigate(`/dashboard/galleries/${gallery.slug}/settings`),
                      },
                      { key: "delete", label: "Delete", danger: true, divider: true, onSelect: () => setPendingDelete(gallery) },
                    ]}
                  />

                  {/* Branding color bar */}
                  <div
                    className="absolute bottom-0 left-0 right-0 h-1"
                    style={{ backgroundColor: gallery.branding_color }}
                  />

                  {/* Password badge */}
                  {gallery.has_password && (
                    <div className="absolute top-3 left-3 bg-white/90 rounded-lg p-1.5 shadow-sm backdrop-blur-sm">
                      <svg
                        className="w-4 h-4 text-muted"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
                        />
                      </svg>
                    </div>
                  )}
                </div>

                {/* Card body */}
                <div className="p-5 flex flex-col flex-1 justify-between gap-4">
                  <div className="space-y-1.5">
                    <h3 className="font-serif text-lg font-bold text-ink group-hover:text-muted transition-colors line-clamp-1">
                      {gallery.title}
                    </h3>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          gallery.is_published
                            ? "bg-brand-green-500"
                            : gallery.photo_count > 0
                              ? "bg-slate-400"
                              : "bg-slate-300"
                        }`}
                      />
                      <p className="text-[10px] text-muted uppercase tracking-wider font-semibold">
                        {gallery.photo_count || 0} image
                        {gallery.photo_count !== 1 ? "s" : ""}
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        navigate(`/dashboard/galleries/${gallery.slug}`)
                      }
                      className="flex-1 py-2.5 border border-cream-200 hover:border-cream-300 hover:bg-cream-100 text-ink text-xs font-medium rounded-xl transition-all cursor-pointer bg-surface-light"
                    >
                      Manage
                    </button>
                    <button
                      type="button"
                      onClick={() => handleGetLink(gallery)}
                      title="Get direct link"
                      aria-label="Get direct link"
                      className="px-3 py-2.5 border border-cream-200 hover:border-cream-300 text-muted hover:text-ink hover:bg-cream-100 rounded-xl transition-all cursor-pointer bg-surface-light"
                    >
                      <svg
                        className="w-3.5 h-3.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ShareLinkModal
        open={linkGallery !== null}
        onClose={() => setLinkGallery(null)}
        url={linkGallery ? resolveShareUrl(username, linkGallery.slug) : ""}
        note={linkGallery && linkGallery.is_published === false ? "This collection is a draft — clients can't open the link until you publish it." : null}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this collection permanently?"
        confirmLabel="Delete permanently"
        busy={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      >
        <p>
          <span className="font-medium text-ink">{pendingDelete?.title}</span>
          {" "}and its {pendingDelete?.photo_count || 0} photo{(pendingDelete?.photo_count || 0) === 1 ? "" : "s"}, sets,
          client activity and every stored file will be removed for good, and the space is freed immediately.
          The client link stops working. This cannot be undone.
        </p>
      </ConfirmDialog>

      {/* ── CREATE GALLERY MODAL ── */}
      <CreateGalleryModal
        isOpen={openCreate}
        onClose={() => setOpenCreate(false)}
        onCreateSubmit={handleCreateSubmit}
      />
    </div>
  );
}
