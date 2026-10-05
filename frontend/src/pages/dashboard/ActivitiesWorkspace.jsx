// frontend/src/pages/dashboard/ActivitiesWorkspace.jsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useOutletContext } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight, Download, Heart } from "lucide-react";
import { formatDateTime } from "../../utils/formatters";
import { galleriesApi } from "../../api/galleriesApi";
import Spinner from "../../components/ui/Spinner";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

const TABS = [
  { id: "downloads", label: "Download Activity" },
  { id: "favorites", label: "Favorite Activity" },
];

// Download Activity sub-tabs, in the order a photographer thinks about them.
const DOWNLOAD_TYPES = [
  { id: "gallery", label: "Gallery" },
  { id: "photo", label: "Single Photo" },
  { id: "video", label: "Single Video" },
];

// DownloadLog.resolution values: 'download' is the Download Master — what a
// client gets when they pick "High Resolution" — and 'original' is the
// untouched upload (only reachable through an explicit original request).
const RESOLUTION_LABELS = { web: "Web Size", download: "High Resolution", original: "Original" };

function EmptyState({ Icon, title, desc }) {
  return (
    <div className="py-16 text-center">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-cream-100">
        <Icon className="h-7 w-7 text-muted" strokeWidth={1.5} aria-hidden="true" />
      </div>
      <p className="mb-1 text-sm text-muted">{title}</p>
      <p className="mx-auto max-w-sm text-xs text-muted">{desc}</p>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div role="alert" className="rounded-xl border border-red-100 bg-red-50 p-6 text-center">
      <p className="text-sm text-red-700">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 cursor-pointer rounded-lg border border-red-200 bg-white px-4 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
      >
        Try again
      </button>
    </div>
  );
}

function PaginationControls({ page, hasNext, hasPrev, onChange, loading }) {
  if (!hasNext && !hasPrev && page === 1) return null;
  return (
    <div className="mt-2 flex items-center justify-center gap-3 border-t border-cream-200 pt-4">
      <button
        type="button"
        disabled={!hasPrev || loading}
        onClick={() => onChange(page - 1)}
        className="cursor-pointer rounded-lg border border-cream-200 px-3 py-1.5 text-xs text-ink hover:bg-cream-100 disabled:opacity-40"
      >
        Previous
      </button>
      <span className="text-xs text-muted">Page {page}</span>
      <button
        type="button"
        disabled={!hasNext || loading}
        onClick={() => onChange(page + 1)}
        className="cursor-pointer rounded-lg border border-cream-200 px-3 py-1.5 text-xs text-ink hover:bg-cream-100 disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}

/** Tab strip used for both the page tabs and the Download Activity sub-tabs. */
function TabStrip({ label, tabs, activeId, onSelect, small = false }) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className={`flex gap-1 overflow-x-auto rounded-xl bg-cream-100 p-1 ${small ? "w-fit max-w-full" : ""}`}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`${label}-${tab.id}`}
          aria-selected={activeId === tab.id}
          onClick={() => onSelect(tab.id)}
          className={`flex-none cursor-pointer rounded-lg px-4 ${small ? "py-2" : "py-2.5"} text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
            activeId === tab.id ? "bg-surface-light text-ink shadow-sm" : "text-muted hover:text-ink"
          }`}
        >
          {tab.label}
          {typeof tab.count === "number" && " "}
          {typeof tab.count === "number" && (
            <span className="ml-1.5 rounded-full bg-cream-200 px-1.5 py-0.5 text-[10px] text-muted">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

const th = "px-4 py-3";
const headRow = "border-b border-cream-200 text-[10px] font-semibold uppercase tracking-wider text-muted";

/** rows shape: DownloadLogSerializer — see apps/clients/serializers.py */
function DownloadTable({ type, rows }) {
  const isGallery = type === "gallery";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className={headRow}>
            <th className={th}>Email</th>
            <th className={th}>{isGallery ? "Download" : type === "video" ? "Video" : "Photo"}</th>
            <th className={th}>{isGallery ? "Sets" : "Set"}</th>
            <th className={th}>Size</th>
            {isGallery && <th className={th}>Photos</th>}
            <th className={th}>PIN</th>
            <th className={th}>Date</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cream-200">
          {rows.map((row) => {
            const filename = row.filename || row.media_asset_name || "";
            return (
              <tr key={row.id} className="text-ink">
                <td className={th}>{row.email || <span className="text-muted">Email not required</span>}</td>
                {isGallery ? (
                  <td className={`${th} max-w-[18rem]`}>
                    <span className="block truncate" title={row.scope}>{row.scope}</span>
                    <span className="block truncate text-xs text-muted" title={filename}>{filename || "File unavailable"}</span>
                  </td>
                ) : (
                  <td className={`${th} max-w-[18rem]`}>
                    <span className="flex items-center gap-3">
                      <span className="h-10 w-10 flex-none overflow-hidden rounded bg-cream-100">
                        {row.thumbnail_url && <img src={row.thumbnail_url} alt="" className="h-full w-full object-cover" />}
                      </span>
                      <span className="min-w-0 truncate" title={filename}>
                        {filename || <span className="text-muted">File removed</span>}
                      </span>
                    </span>
                  </td>
                )}
                <td className={`${th} max-w-[14rem] text-muted`}>
                  <span className="block truncate" title={row.photo_set_name || ""}>
                    {row.photo_set_name || (isGallery ? "—" : "All photos")}
                  </span>
                </td>
                <td className={th}>{RESOLUTION_LABELS[row.resolution] || row.resolution}</td>
                {isGallery && <td className={`${th} text-muted`}>{row.photo_count ?? "—"}</td>}
                <td className={`${th} text-muted`}>{row.pin_state === "verified" ? "Verified" : "Not required"}</td>
                <td className={`${th} whitespace-nowrap text-muted`}>{formatDateTime(row.created_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** rows shape: favorite lists grouped by visitor — see apps/clients/favorite_lists.py */
function FavoriteVisitorTable({ rows, onOpen }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const toggle = (id) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className={headRow}>
            <th className={th}>Visitor</th>
            <th className={th}>Lists</th>
            <th className={th}>Photos</th>
            <th className={th}>Created</th>
            <th className={th}>Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cream-200">
          {rows.map((visitor) => {
            const isOpen = expanded.has(visitor.id);
            const Chevron = isOpen ? ChevronDown : ChevronRight;
            return [
              <tr key={visitor.id} className="text-ink">
                <td className={th}>
                  <button
                    type="button"
                    onClick={() => toggle(visitor.id)}
                    aria-expanded={isOpen}
                    aria-label={`${isOpen ? "Hide" : "Show"} favorite lists of ${visitor.email || "Guest"}`}
                    className="flex cursor-pointer items-center gap-2 rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
                  >
                    <Chevron className="h-4 w-4 flex-none text-muted" aria-hidden="true" />
                    <span>
                      <span className="block">{visitor.email || <span className="text-muted">Guest</span>}</span>
                      {visitor.name && <span className="block text-xs text-muted">{visitor.name}</span>}
                    </span>
                  </button>
                </td>
                <td className={th}>{visitor.list_count}</td>
                <td className={th}>{visitor.total_photos}</td>
                <td className={`${th} whitespace-nowrap text-muted`}>{formatDateTime(visitor.created_at)}</td>
                <td className={`${th} whitespace-nowrap text-muted`}>{formatDateTime(visitor.updated_at)}</td>
              </tr>,
              isOpen && (
                <tr key={`${visitor.id}-lists`} className="bg-cream-50">
                  <td colSpan={5} className="px-4 pb-4 pt-1">
                    <ul className="divide-y divide-cream-200 rounded-xl border border-cream-200 bg-surface-light">
                      {visitor.lists.map((list) => (
                        <li key={list.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
                          <span className="h-12 w-12 flex-none overflow-hidden rounded bg-cream-100">
                            {list.thumbnail_url && <img src={list.thumbnail_url} alt="" className="h-full w-full object-cover" />}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-ink">{list.name}</span>
                            <span className="block text-xs text-muted">
                              {list.photo_count} photo{list.photo_count === 1 ? "" : "s"} · created {formatDateTime(list.created_at)} · updated {formatDateTime(list.updated_at)}
                            </span>
                          </span>
                          <button
                            type="button"
                            onClick={() => onOpen(list, visitor)}
                            className="cursor-pointer rounded-lg border border-cream-200 px-3 py-1.5 text-xs text-ink hover:bg-cream-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
                          >
                            View photos
                          </button>
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

/** rows shape: PhotographerFavoriteSerializer — the photos inside one list */
function FavoritePhotoGrid({ rows }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {rows.map((row) => (
        <div key={row.id} className="overflow-hidden rounded-xl border border-cream-200 bg-cream-50">
          <div className="aspect-square bg-cream-100">
            {row.thumbnail_url && <img src={row.thumbnail_url} alt={row.original_name || ""} className="h-full w-full object-cover" />}
          </div>
          <div className="p-2 text-[11px]">
            <p className="truncate text-ink" title={row.original_name || ""}>{row.original_name || "Photo"}</p>
            <p className="text-muted">{formatDateTime(row.created_at)}</p>
            {row.set_name && <p className="truncate text-muted" title={row.set_name}>{row.set_name}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ActivitiesWorkspace() {
  const { slug } = useOutletContext();

  // The active tab lives in the URL (?tab=favorites) so a refresh or a
  // shared link lands on the same tab. Unknown values fall back to the first.
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const activeId = TABS.some((t) => t.id === requested) ? requested : TABS[0].id;
  const selectTab = (id) => setSearchParams({ tab: id }, { replace: true });

  const isMountedRef = useRef(true);
  // Re-armed on mount: React StrictMode (dev) mounts, unmounts, then mounts
  // again, and a cleanup-only effect would leave this stuck at false.
  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  // ── Download Activity ────────────────────────────────────────────────────
  const [downloadType, setDownloadType] = useState("gallery");
  const [downloadRows, setDownloadRows] = useState([]);
  const [downloadCounts, setDownloadCounts] = useState(null);
  const [downloadPage, setDownloadPage] = useState(1);
  const [downloadHasNext, setDownloadHasNext] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const autoPickedRef = useRef(false);

  const loadDownloads = useCallback(async (type, page) => {
    if (USE_MOCK_DATA || !slug) return;
    setDownloadLoading(true);
    setDownloadError("");
    try {
      const data = await galleriesApi.getDownloadLogs(slug, page, type);
      if (!isMountedRef.current) return;
      // First load only: if the default tab is empty but another has activity,
      // land on the first tab that has something instead of an empty table.
      if (!autoPickedRef.current && type === "gallery" && data.counts && data.counts.gallery === 0) {
        const firstWithRows = DOWNLOAD_TYPES.find((t) => data.counts[t.id] > 0);
        autoPickedRef.current = true;
        if (firstWithRows) {
          setDownloadCounts(data.counts);
          setDownloadType(firstWithRows.id);
          return;
        }
      }
      autoPickedRef.current = true;
      setDownloadRows(data.results || []);
      setDownloadCounts(data.counts || null);
      setDownloadHasNext(Boolean(data.next));
      setDownloadPage(page);
    } catch {
      if (isMountedRef.current) setDownloadError("Could not load download activity.");
    } finally {
      if (isMountedRef.current) setDownloadLoading(false);
    }
  }, [slug]);

  // ── Favorite Activity (lists, then one list's photos) ────────────────────
  const [lists, setLists] = useState([]);
  const [emailFilter, setEmailFilter] = useState("");
  const [appliedEmail, setAppliedEmail] = useState("");
  const [favSort, setFavSort] = useState("newest");
  const [listPage, setListPage] = useState(1);
  const [listHasNext, setListHasNext] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");

  const [openList, setOpenList] = useState(null);
  const [listPhotos, setListPhotos] = useState([]);
  const [photoPage, setPhotoPage] = useState(1);
  const [photoHasNext, setPhotoHasNext] = useState(false);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [photoError, setPhotoError] = useState("");

  const loadLists = useCallback(async (page) => {
    if (USE_MOCK_DATA || !slug) return;
    setListLoading(true);
    setListError("");
    try {
      const data = await galleriesApi.getFavoriteVisitors(slug, page, { email: appliedEmail, sort: favSort });
      if (!isMountedRef.current) return;
      setLists(data.results || []);
      setListHasNext(Boolean(data.next));
      setListPage(page);
    } catch {
      if (isMountedRef.current) setListError("Could not load favorite activity.");
    } finally {
      if (isMountedRef.current) setListLoading(false);
    }
  }, [slug, appliedEmail, favSort]);

  const loadListPhotos = useCallback(async (listId, page) => {
    setPhotoLoading(true);
    setPhotoError("");
    try {
      const data = await galleriesApi.getFavoriteListPhotos(slug, listId, page);
      if (!isMountedRef.current) return;
      setListPhotos(data.results || []);
      setPhotoHasNext(Boolean(data.next));
      setPhotoPage(page);
    } catch {
      if (isMountedRef.current) setPhotoError("Could not load this favorite list.");
    } finally {
      if (isMountedRef.current) setPhotoLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (activeId === "downloads") loadDownloads(downloadType, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, slug, downloadType]);

  useEffect(() => {
    if (activeId === "favorites") loadLists(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, slug, appliedEmail, favSort]);

  // The email filter applies shortly after typing stops, not on every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedEmail(emailFilter.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [emailFilter]);

  const handleOpenList = (list, visitor) => {
    const row = { ...list, email: visitor?.email || null };
    setOpenList(row);
    setListPhotos([]);
    loadListPhotos(row.id, 1);
  };

  const downloadTabs = DOWNLOAD_TYPES.map((t) => ({ ...t, count: downloadCounts ? downloadCounts[t.id] : undefined }));

  return (
    <div className="space-y-6">
      <TabStrip label="Collection activity" tabs={TABS} activeId={activeId} onSelect={selectTab} />

      <div
        role="tabpanel"
        aria-labelledby={`Collection activity-${activeId}`}
        className="rounded-2xl border border-cream-200 bg-surface-light p-6 shadow-card"
      >
        {activeId === "downloads" && (
          <div className="space-y-5">
            <TabStrip
              label="Download type"
              tabs={downloadTabs}
              activeId={downloadType}
              onSelect={(id) => { setDownloadType(id); setDownloadRows([]); }}
              small
            />
            {downloadError ? (
              <ErrorState message={downloadError} onRetry={() => loadDownloads(downloadType, downloadPage)} />
            ) : downloadLoading && downloadRows.length === 0 ? (
              <div className="flex justify-center py-16" role="status" aria-label="Loading download activity"><Spinner size="lg" /></div>
            ) : downloadRows.length === 0 ? (
              <EmptyState
                Icon={Download}
                title={`No ${DOWNLOAD_TYPES.find((t) => t.id === downloadType).label.toLowerCase()} downloads yet`}
                desc="When a client downloads from this collection, their email and the date will be listed here."
              />
            ) : (
              <>
                <DownloadTable type={downloadType} rows={downloadRows} />
                <PaginationControls
                  page={downloadPage}
                  hasNext={downloadHasNext}
                  hasPrev={downloadPage > 1}
                  onChange={(page) => loadDownloads(downloadType, page)}
                  loading={downloadLoading}
                />
              </>
            )}
          </div>
        )}

        {activeId === "favorites" && !openList && (
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <h2 className="font-serif text-xl text-ink">Favorite Activity</h2>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="search"
                value={emailFilter}
                onChange={(event) => setEmailFilter(event.target.value)}
                placeholder="Filter by email"
                aria-label="Filter favorites by email"
                className="w-48 rounded-lg border border-cream-200 bg-white px-3 py-1.5 text-xs text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
              />
              <label className="flex items-center gap-2 text-xs text-muted">
                Sort
                <select
                  value={favSort}
                  onChange={(event) => setFavSort(event.target.value)}
                  aria-label="Sort favorite activity"
                  className="rounded-lg border border-cream-200 bg-white px-2 py-1.5 text-xs text-ink"
                >
                  <option value="newest">Newest</option>
                  <option value="oldest">Oldest</option>
                  <option value="email">Email</option>
                </select>
              </label>
            </div>
          </div>
        )}

        {activeId === "favorites" && !openList && (
          listError ? (
            <ErrorState message={listError} onRetry={() => loadLists(listPage)} />
          ) : listLoading && lists.length === 0 ? (
            <div className="flex justify-center py-16" role="status" aria-label="Loading favorite activity"><Spinner size="lg" /></div>
          ) : lists.length === 0 ? (
            <EmptyState
              Icon={Heart}
              title={appliedEmail ? "No favorites match that email" : "No favorite activity"}
              desc={appliedEmail ? "Try a different email, or clear the filter." : "When a client favorites photos in this collection, their list will appear here."}
            />
          ) : (
            <>
              <FavoriteVisitorTable rows={lists} onOpen={handleOpenList} />
              <PaginationControls
                page={listPage}
                hasNext={listHasNext}
                hasPrev={listPage > 1}
                onChange={loadLists}
                loading={listLoading}
              />
            </>
          )
        )}

        {activeId === "favorites" && openList && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setOpenList(null)}
                className="flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
              >
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                All favorite lists
              </button>
              <p className="text-sm text-ink">
                {openList.email || "Guest"} · {openList.name}
                <span className="ml-2 text-xs text-muted">
                  {openList.photo_count} photo{openList.photo_count === 1 ? "" : "s"} · updated {formatDateTime(openList.updated_at)}
                </span>
              </p>
            </div>
            {photoError ? (
              <ErrorState message={photoError} onRetry={() => loadListPhotos(openList.id, photoPage)} />
            ) : photoLoading && listPhotos.length === 0 ? (
              <div className="flex justify-center py-16" role="status" aria-label="Loading favorites"><Spinner size="lg" /></div>
            ) : listPhotos.length === 0 ? (
              <EmptyState Icon={Heart} title="This list is empty" desc="The client has removed all of their favorites." />
            ) : (
              <>
                <FavoritePhotoGrid rows={listPhotos} />
                <PaginationControls
                  page={photoPage}
                  hasNext={photoHasNext}
                  hasPrev={photoPage > 1}
                  onChange={(page) => loadListPhotos(openList.id, page)}
                  loading={photoLoading}
                />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
