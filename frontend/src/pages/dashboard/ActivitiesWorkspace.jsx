import { useState } from "react";
import { useOutletContext } from "react-router-dom";

const ACTIVITY_TABS = [
  { id: "downloads", label: "Download Activity" },
  { id: "favorites", label: "Favorites" },
  { id: "store", label: "Store Orders" },
  { id: "email", label: "Email Registration" },
  { id: "contacts", label: "Marketing Contacts" },
  { id: "links", label: "Quick Share Links" },
  { id: "private", label: "Private Photos" },
];

const DOWNLOAD_CATEGORIES = [
  { id: "gallery", label: "Gallery", icon: "camera" },
  { id: "single-photo", label: "Single Photo", icon: "image" },
  { id: "single-video", label: "Single Video", icon: "video" },
];

export default function ActivitiesWorkspace() {
  const { gallery } = useOutletContext();
  const [activeTab, setActiveTab] = useState("downloads");
  const [downloadCategory, setDownloadCategory] = useState("gallery");

  return (
    <div className="space-y-6">
      {/* Tab bar */}
      <div className="flex gap-1 bg-slate-100 rounded-xl p-1 overflow-x-auto">
        {ACTIVITY_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-none px-4 py-2.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${
              activeTab === tab.id
                ? "bg-white text-ink shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Downloads Tab */}
      {activeTab === "downloads" && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-9 h-9 rounded-xl bg-teal-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-teal-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
            </div>
            <div>
              <h2 className="font-serif text-lg text-ink">Download Activity</h2>
              <p className="text-xs text-muted">Track client download behavior across this collection.</p>
            </div>
          </div>

          {/* Category sub-tabs */}
          <div className="flex gap-2 mb-6">
            {DOWNLOAD_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setDownloadCategory(cat.id)}
                className={`px-4 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer ${
                  downloadCategory === cat.id
                    ? "bg-teal-500/10 border-teal-500/30 text-teal-700"
                    : "bg-white border-slate-200 text-muted hover:border-slate-300 hover:text-ink"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-3 gap-3 mb-6">
            {[
              { label: "Total Downloads", value: gallery?.download_count || 0 },
              { label: "Unique Visitors", value: gallery?.visitor_count || 0 },
              { label: "Favorites", value: gallery?.favorite_count || 0 },
            ].map((stat) => (
              <div key={stat.label} className="p-4 bg-slate-50 rounded-xl border border-slate-100 text-center">
                <p className="font-serif text-2xl text-ink">{stat.value}</p>
                <p className="text-[10px] text-muted uppercase tracking-wider font-semibold mt-1">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Empty state */}
          <div className="py-12 text-center">
            <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
              </svg>
            </div>
            <p className="text-sm text-muted font-light mb-1">No download activity yet</p>
            <p className="text-xs text-muted/60">Activity will appear here once clients start accessing this gallery.</p>
          </div>
        </div>
      )}

      {/* Favorites Tab */}
      {activeTab === "favorites" && (
        <EmptyState
          icon="heart"
          title="No favorite activity"
          desc="Client favorites will appear here."
        />
      )}

      {/* Store Tab */}
      {activeTab === "store" && (
        <EmptyState
          icon="store"
          title="No store orders"
          desc="Print orders will appear here once the store is enabled."
        />
      )}

      {/* Email Tab */}
      {activeTab === "email" && (
        <EmptyState
          icon="email"
          title="No email registrations"
          desc="Client email signups will appear here."
        />
      )}

      {/* Contacts Tab */}
      {activeTab === "contacts" && (
        <EmptyState
          icon="contacts"
          title="No marketing contacts"
          desc="Collected contacts will appear here."
        />
      )}

      {/* Links Tab */}
      {activeTab === "links" && (
        <EmptyState
          icon="link"
          title="No quick share links"
          desc="Generated share links will appear here."
        />
      )}

      {/* Private Tab */}
      {activeTab === "private" && (
        <EmptyState
          icon="lock"
          title="No private photos"
          desc="Privately shared photos will appear here."
        />
      )}
    </div>
  );
}

function EmptyState({ icon, title, desc }) {
  const icons = {
    heart: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
      </svg>
    ),
    store: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016A3.001 3.001 0 0021 9.349" />
      </svg>
    ),
    email: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
    contacts: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
      </svg>
    ),
    link: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
      </svg>
    ),
    lock: (
      <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
      </svg>
    ),
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
      <div className="py-12 text-center">
        <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
          {icons[icon]}
        </div>
        <p className="text-sm text-muted font-light mb-1">{title}</p>
        <p className="text-xs text-muted/60">{desc}</p>
      </div>
    </div>
  );
}
