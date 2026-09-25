// frontend/src/pages/dashboard/ActivitiesWorkspace.jsx
import { useSearchParams } from "react-router-dom";
import { Download, Heart, Lock } from "lucide-react";
import { formatDate } from "../../utils/formatters";

const TABS = [
  { id: "downloads", label: "Download Activity" },
  { id: "favorites", label: "Favorite Activity" },
  { id: "private", label: "Private Photos" },
];

function EmptyState({ Icon, title, desc }) {
  return (
    <div className="py-16 text-center">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
        <Icon className="h-7 w-7 text-slate-400" strokeWidth={1.5} aria-hidden="true" />
      </div>
      <p className="mb-1 text-sm text-slate-600">{title}</p>
      <p className="mx-auto max-w-sm text-xs text-slate-400">{desc}</p>
    </div>
  );
}

/**
 * rows shape mirrors the backend DownloadLog model:
 *   { id, email, created_at }
 * There is no API endpoint for it yet, so the caller passes [] for now.
 */
function DownloadActivityPanel({ rows = [] }) {
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
          <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <th className="px-4 py-3">Email</th>
            <th className="px-4 py-3">Date downloaded</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.id} className="text-ink">
              <td className="px-4 py-3">{row.email}</td>
              <td className="px-4 py-3 text-slate-500">{formatDate(row.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ActivitiesWorkspace() {
  // The active tab lives in the URL (?tab=favorites) so a refresh or a
  // shared link lands on the same tab. Unknown values fall back to the first.
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const activeId = TABS.some((t) => t.id === requested) ? requested : TABS[0].id;

  const selectTab = (id) => setSearchParams({ tab: id }, { replace: true });

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Collection activity" className="flex gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeId === tab.id}
            aria-controls={`panel-${tab.id}`}
            onClick={() => selectTab(tab.id)}
            className={`flex-none cursor-pointer rounded-lg px-4 py-2.5 text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 ${
              activeId === tab.id
                ? "bg-white text-ink shadow-sm"
                : "text-slate-500 hover:text-ink"
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
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card"
      >
        {activeId === "downloads" && <DownloadActivityPanel rows={[]} />}
        {activeId === "favorites" && (
          <EmptyState
            Icon={Heart}
            title="No favorite activity"
            desc="Photos your clients mark as favorites will appear here."
          />
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