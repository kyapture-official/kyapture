// frontend/src/pages/dashboard/ActivitiesWorkspace.jsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useOutletContext } from "react-router-dom";
import { Download, Heart, Lock } from "lucide-react";
import { formatDate } from "../../utils/formatters";
import { galleriesApi } from "../../api/galleriesApi";
import Spinner from "../../components/ui/Spinner";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

const TABS = [
  { id: "downloads", label: "Download Activity" },
  { id: "favorites", label: "Favorite Activity" },
  { id: "private", label: "Private Photos" },
];

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

const RESOLUTION_LABELS = { web: "Web Size", original: "High Resolution" };
const DOWNLOAD_TYPE_LABELS = { gallery: "Full Gallery", photo: "Single Photo", video: "Single Video" };

/** rows shape: DownloadLogSerializer — see apps/clients/serializers.py */
function DownloadActivityPanel({ rows, pagination }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        Icon={Download}
        title="No download activity yet"
        desc="When a client downloads this collection, their email and the date will be listed here."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-cream-200 text-[10px] font-semibold uppercase tracking-wider text-muted">
            <th className="px-4 py-3">Email</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Resolution</th>
            <th className="px-4 py-3">Set</th>
            <th className="px-4 py-3">PIN</th>
            <th className="px-4 py-3">Date</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-cream-200">
          {rows.map((row) => (
            <tr key={row.id} className="text-ink">
              <td className="px-4 py-3">{row.email || <span className="text-muted">— (frictionless)</span>}</td>
              <td className="px-4 py-3">{DOWNLOAD_TYPE_LABELS[row.download_type] || row.download_type}</td>
              <td className="px-4 py-3">{RESOLUTION_LABELS[row.resolution] || row.resolution}</td>
              <td className="px-4 py-3 text-muted">{row.photo_set_name || "—"}</td>
              <td className="px-4 py-3 text-muted">{row.pin_verified ? "Verified" : "—"}</td>
              <td className="px-4 py-3 text-muted">{formatDate(row.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {pagination}
    </div>
  );
}

/** rows shape: PhotographerFavoriteSerializer — see apps/clients/serializers.py */
function FavoriteActivityPanel({ rows, pagination }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        Icon={Heart}
        title="No favorite activity"
        desc="Photos your clients mark as favorites will appear here."
      />
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {rows.map((row) => (
          <div key={row.id} className="rounded-xl overflow-hidden border border-cream-200 bg-cream-50">
            <div className="aspect-square bg-cream-100">
              {row.thumbnail_url && (
                <img src={row.thumbnail_url} alt="" className="w-full h-full object-cover" />
              )}
            </div>
            <div className="p-2 text-[11px]">
              <p className="text-ink truncate">{row.email || "Anonymous"}</p>
              <p className="text-muted">{formatDate(row.created_at)}</p>
            </div>
          </div>
        ))}
      </div>
      {pagination}
    </div>
  );
}

function PaginationControls({ page, hasNext, hasPrev, onChange, loading }) {
  if (!hasNext && !hasPrev && page === 1) return null;
  return (
    <div className="flex items-center justify-center gap-3 pt-4 mt-2 border-t border-cream-200">
      <button
        type="button"
        disabled={!hasPrev || loading}
        onClick={() => onChange(page - 1)}
        className="text-xs px-3 py-1.5 rounded-lg border border-cream-200 text-ink disabled:opacity-40 hover:bg-cream-100 cursor-pointer"
      >
        Previous
      </button>
      <span className="text-xs text-muted">Page {page}</span>
      <button
        type="button"
        disabled={!hasNext || loading}
        onClick={() => onChange(page + 1)}
        className="text-xs px-3 py-1.5 rounded-lg border border-cream-200 text-ink disabled:opacity-40 hover:bg-cream-100 cursor-pointer"
      >
        Next
      </button>
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

  const [downloadRows, setDownloadRows] = useState([]);
  const [downloadPage, setDownloadPage] = useState(1);
  const [downloadHasNext, setDownloadHasNext] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);

  const [favoriteRows, setFavoriteRows] = useState([]);
  const [favoritePage, setFavoritePage] = useState(1);
  const [favoriteHasNext, setFavoriteHasNext] = useState(false);
  const [favoriteLoading, setFavoriteLoading] = useState(false);

  const isMountedRef = useRef(true);
  useEffect(() => () => { isMountedRef.current = false; }, []);

  const loadDownloads = useCallback(async (page) => {
    if (USE_MOCK_DATA || !slug) return;
    setDownloadLoading(true);
    try {
      const data = await galleriesApi.getDownloadLogs(slug, page);
      if (isMountedRef.current) {
        setDownloadRows(data.results || []);
        setDownloadHasNext(Boolean(data.next));
        setDownloadPage(page);
      }
    } catch {
      // Leave the previous page visible rather than clearing it on a
      // transient network error.
    } finally {
      if (isMountedRef.current) setDownloadLoading(false);
    }
  }, [slug]);

  const loadFavorites = useCallback(async (page) => {
    if (USE_MOCK_DATA || !slug) return;
    setFavoriteLoading(true);
    try {
      const data = await galleriesApi.getFavoriteActivity(slug, page);
      if (isMountedRef.current) {
        setFavoriteRows(data.results || []);
        setFavoriteHasNext(Boolean(data.next));
        setFavoritePage(page);
      }
    } catch {
      // Same rationale as loadDownloads above.
    } finally {
      if (isMountedRef.current) setFavoriteLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (activeId === "downloads") loadDownloads(1);
    if (activeId === "favorites") loadFavorites(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, slug]);

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Collection activity" className="flex gap-1 overflow-x-auto rounded-xl bg-cream-100 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeId === tab.id}
            aria-controls={`panel-${tab.id}`}
            onClick={() => selectTab(tab.id)}
            className={`flex-none cursor-pointer rounded-lg px-4 py-2.5 text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
              activeId === tab.id
                ? "bg-surface-light text-ink shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`panel-${activeId}`}
        aria-labelledby={`tab-${activeId}`}
        className="rounded-2xl border border-cream-200 bg-surface-light p-6 shadow-card"
      >
        {activeId === "downloads" && (
          downloadLoading && downloadRows.length === 0 ? (
            <div className="py-16 flex justify-center"><Spinner size="lg" /></div>
          ) : (
            <DownloadActivityPanel
              rows={downloadRows}
              pagination={
                <PaginationControls
                  page={downloadPage}
                  hasNext={downloadHasNext}
                  hasPrev={downloadPage > 1}
                  onChange={loadDownloads}
                  loading={downloadLoading}
                />
              }
            />
          )
        )}
        {activeId === "favorites" && (
          favoriteLoading && favoriteRows.length === 0 ? (
            <div className="py-16 flex justify-center"><Spinner size="lg" /></div>
          ) : (
            <FavoriteActivityPanel
              rows={favoriteRows}
              pagination={
                <PaginationControls
                  page={favoritePage}
                  hasNext={favoriteHasNext}
                  hasPrev={favoritePage > 1}
                  onChange={loadFavorites}
                  loading={favoriteLoading}
                />
              }
            />
          )
        )}
        {activeId === "private" && (
          <EmptyState
            Icon={Lock}
            title="No private photos"
            desc="Photos you share privately will appear here."
          />
        )}
      </div>
    </div>
  );
}