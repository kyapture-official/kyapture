// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/layout/CollectionSidebar.jsx
import { NavLink, Link } from "react-router-dom";
import { formatDate } from "../../utils/formatters";

export default function CollectionSidebar({ gallery }) {
  return (
    <aside className="w-full md:w-72 md:min-h-screen flex-shrink-0 bg-white border-b md:border-b-0 md:border-r border-cream-200 px-5 py-6 flex flex-col">
      <div className="mb-5">
        <h2 className="font-serif text-xl text-ink font-semibold truncate">
          {gallery.title}
        </h2>
        <p className="text-xs text-muted mt-0.5">
          {new Date(gallery.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </p>
      </div>

      {/* Big rectangular cover — matches your Pixieset reference */}
      <div className="w-full aspect-[4/3] rounded-xl overflow-hidden bg-cream-100 mb-6 border border-cream-200">
        {gallery.cover_url ? (
          <img
            src={gallery.cover_url}
            alt={`${gallery.title} cover`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ backgroundColor: gallery.branding_color || "#4a7c6f" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeOpacity="0.6"
              strokeWidth="1.5"
            >
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </div>
        )}
      </div>

      <nav className="flex flex-row md:flex-col gap-1">
        <NavLink
          to={`/dashboard/galleries/${gallery.slug}`}
          end
          className={({ isActive }) =>
            `flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              isActive ? "bg-ink text-white" : "text-ink/70 hover:bg-cream-100"
            }`
          }
        >
          Photos
        </NavLink>
        <NavLink
          to={`/dashboard/galleries/${gallery.slug}/settings`}
          className={({ isActive }) =>
            `flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              isActive ? "bg-ink text-white" : "text-ink/70 hover:bg-cream-100"
            }`
          }
        >
          Settings
        </NavLink>
      </nav>

      <div className="mt-auto pt-6">
        <Link
          to="/dashboard/galleries"
          className="flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors"
        >
          ← Back to Collections
        </Link>
      </div>
    </aside>
  );
}
