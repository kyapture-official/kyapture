import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Images,
  Brush,
  Settings,
  Rss,
  ChevronLeft,
  Camera,
  Plus,
  GripVertical,
  MoreHorizontal,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "", end: true, label: "Photos", Icon: Images },
  { to: "design", label: "Design", Icon: Brush },
  { to: "settings", label: "Settings", Icon: Settings },
  { to: "activities", label: "Activities", Icon: Rss },
];

const resolvePath = (basePath, to) => (to ? `${basePath}/${to}` : basePath);

function RailTooltip({ children }) {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 z-50"
    >
      <span className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-slate-900" />
      {children}
    </span>
  );
}

function CollectionCover({ gallery }) {
  const coverUrl = gallery?.cover_url ?? null;
  const title = gallery?.title || "Collection";
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [coverUrl]);

  if (coverUrl && !failed) {
    return (
      <img
        src={coverUrl}
        alt={`${title} cover`}
        onError={() => setFailed(true)}
        className="h-[180px] w-full object-cover"
      />
    );
  }

  return (
    <div
      className="flex h-[180px] w-full items-center justify-center bg-slate-100"
      style={{ backgroundColor: gallery?.branding_color || "#0D9488" }}
    >
      <Camera className="h-8 w-8 text-white/70" aria-hidden="true" />
    </div>
  );
}

export default function GallerySecondarySidebar({ basePath, gallery }) {
  const navigate = useNavigate();

  return (
    <>
      {/* DESKTOP SIDEBAR */}
      <aside
        aria-label="Collection navigation"
        className="sticky top-0 z-30 hidden h-screen w-[300px] flex-shrink-0 flex-col border-r border-slate-200 bg-white md:flex"
      >
        {/* 1. TOP HEADER: Back arrow, Title, Date & Published tag */}
        <div className="flex items-center p-3.5 border-b border-slate-200">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <button
              type="button"
              onClick={() => navigate("/dashboard/galleries")}
              className="text-slate-500 hover:text-slate-800 transition-colors cursor-pointer shrink-0"
              aria-label="Back to collections"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="truncate">
              <h2 className="text-sm font-semibold text-slate-900 truncate leading-tight">
                {gallery?.title || "sari and ravi"}
              </h2>
              <p className="text-[11px] text-slate-400">
                {gallery?.created_at
                  ? new Date(gallery.created_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })
                  : "Aug 1, 2026"}
              </p>
            </div>
          </div>
        </div>

        {/* 2. COVER IMAGE */}
        <CollectionCover gallery={gallery} />

        {/* 3. ICON NAVIGATION */}
        <nav className="flex items-center justify-between border-b border-slate-200 px-5 py-2.5">
          {NAV_ITEMS.map(({ to, end, label, Icon }) => (
            <NavLink
              key={label}
              to={resolvePath(basePath, to)}
              end={end}
              aria-label={label}
              className={({ isActive }) =>
                `group relative flex items-center justify-center p-1.5 transition-colors ${
                  isActive
                    ? "text-slate-900 border-b-2 border-emerald-500 pb-2 -mb-2.5"
                    : "text-slate-400 hover:text-slate-700"
                }`
              }
            >
              <Icon className="h-5 w-5" strokeWidth={1.75} />
              <RailTooltip>{label}</RailTooltip>
            </NavLink>
          ))}
        </nav>

        {/* 4. SETS LIST */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-bold text-slate-400 tracking-wider">
              PHOTOS
            </span>
            <button
              type="button"
              className="flex items-center gap-1 text-xs font-medium text-emerald-600 hover:text-emerald-700 cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" /> Add Set
            </button>
          </div>

          <div className="flex items-center justify-between p-2.5 bg-slate-50 rounded-md cursor-pointer hover:bg-slate-100 transition-colors border border-slate-100">
            <div className="flex items-center gap-2.5">
              <GripVertical className="h-4 w-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-800">
                Highlights (51)
              </span>
            </div>
            <MoreHorizontal className="h-4 w-4 text-slate-400" />
          </div>
        </div>
      </aside>

      {/* MOBILE BOTTOM TABS */}
      <nav
        aria-label="Collection sections"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      >
        {NAV_ITEMS.map(({ to, end, label, Icon }) => (
          <NavLink
            key={label}
            to={resolvePath(basePath, to)}
            end={end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] font-medium ${
                isActive ? "text-emerald-600" : "text-slate-400"
              }`
            }
          >
            <Icon className="h-5 w-5" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
